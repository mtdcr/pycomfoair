#
# Copyright (c) 2020 Andreas Oberritter
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import asyncio
import logging
from bitstring import BitArray
from datetime import datetime
from struct import pack
from urllib.parse import urlparse
from async_timeout import timeout
from serial import SerialException
from serial_asyncio import create_serial_connection
from . import ComfoAirBase

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class CACommand(asyncio.Event):
    def __init__(self, loop, cmd: int, data: bytes = None):
        super().__init__(loop=loop)
        self._cmd = cmd
        self._data = data

    @property
    def cmd(self) -> int:
        return self._cmd

    @property
    def data(self) -> bytes:
        return self._data


class CACommandPair:
    def __init__(self, tx: CACommand, rx: CACommand = None):
        self._tx = tx
        self._rx = rx

    @property
    def tx(self) -> CACommand:
        return self._tx

    @property
    def rx(self) -> CACommand:
        return self._rx


class ComfoAir(ComfoAirBase, asyncio.Protocol):
    def __init__(self, url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._url = urlparse(url)
        self._transport = None
        self._cooked_listeners = {}
        self._cooked_cache = {}
        self._raw_listeners = set()
        self._raw_cache = {}
        self._loop = None
        self._rx_queue = None
        self._rx_task = None
        self._tx_queue = None
        self._tx_task = None
        self._running = False
        self._buf = b''
        self._cmd = None
        self._lock = None

    def _geturl(self):
        return self._url.geturl()

    async def _resume_reading(self, delay):
        await asyncio.sleep(delay, loop=self._loop)
        if self._transport:
            self._transport.resume_reading()

    def _delay_reading(self, delay):
        self._transport.pause_reading()
        asyncio.ensure_future(self._resume_reading(delay), loop=self._loop)

    def data_received(self, data: bytes):
        self._rx_queue.put_nowait(data)
        self._delay_reading(1)

    def connection_lost(self, exc: Exception):
        logger.warning('Lost connection to %s: %s', self._geturl(), exc)
        if self._running and not self._lock.locked():
            asyncio.ensure_future(
                self._reconnect(delay=10),
                loop=self._loop
            )

    @staticmethod
    def _flush_queue(queue):
        while not queue.empty():
            queue.get_nowait()

        while True:
            try:
                queue.task_done()
            except ValueError:
                break

    async def _create_connection(self):
        if self._url.scheme == 'socket':
            kwargs = {
                'host': self._url.hostname,
                'port': self._url.port,
            }
            return await self._loop.create_connection(lambda: self, **kwargs)

        kwargs = {
            'url': self._geturl(),
            'baudrate': self._BAUD_RATE,
        }
        return await create_serial_connection(self._loop, lambda: self, **kwargs)

    async def _reconnect(self, delay: int = 0):
        async with self._lock:
            await self._disconnect()
            self._flush_queue(self._rx_queue)

            await asyncio.sleep(delay, loop=self._loop)

            logger.info('Connecting to %s', self._geturl())
            try:
                async with timeout(5, loop=self._loop):
                    self._transport, _ = await self._create_connection()
            except (BrokenPipeError, ConnectionRefusedError,
                    SerialException, asyncio.TimeoutError) as exc:
                logger.warning(exc)
                asyncio.ensure_future(
                    self._reconnect(delay=10),
                    loop=self._loop
                )
            else:
                logger.info('Connected to %s', self._geturl())

    def _write(self, msg):
        if not self._transport:
            logger.warning('Transport unavailable!')
            return False

        self._transport.write(msg)
        return True

    async def _tx_worker(self):
        while self._running:
            self._cmd = await self._tx_queue.get()
            msg = self._create_msg(self._cmd.tx.cmd, self._cmd.tx.data)

            for tries in range(10):
                self._cmd.tx.clear()

                logger.debug('Write #%d %#x %s',
                             tries + 1, self._cmd.tx.cmd,
                             self._cmd.tx.data.hex())

                if not self._write(msg):
                    break

                try:
                    async with timeout(1, loop=self._loop):
                        await self._cmd.tx.wait()
                except asyncio.TimeoutError:
                    logger.warning('TX ack timeout')
                    continue

                logger.debug('ACK ok')
                if self._cmd.rx is None:
                    break

                try:
                    async with timeout(1, loop=self._loop):
                        await self._cmd.rx.wait()
                except asyncio.TimeoutError:
                    logger.warning('RX msg timeout')
                    continue

                logger.debug('message ok (bufsize=%d)', len(self._buf))
                self._write(self._ack())
                break

            self._tx_queue.task_done()
            self._cmd = None

    async def _transaction(self, cmd: CACommandPair) -> None:
        switch_to_pc_mode = CACommandPair(
            CACommand(self._loop, 0x9b, b'\x03'),
            CACommand(self._loop, 0x9c, b'\x03')
        )
        switch_to_cc_ease_mode = CACommandPair(
            CACommand(self._loop, 0x9b, b'\x00'),
            CACommand(self._loop, 0x9c, b'\x02')
        )

        for cmdpair in (switch_to_pc_mode, cmd, switch_to_cc_ease_mode):
            await self._tx_queue.put(cmdpair)

    async def _cook_cmd(self, cmd, data):
        if not self._cooked_listeners:
            return

        if self._raw_cache.get(cmd) == data:
            return
        self._raw_cache[cmd] = data

        for attr, callbacks in self._cooked_listeners.items():
            if attr.cmd == cmd:
                bits = BitArray(data)
                value = bits[attr.offset:attr.offset + attr.size].uint

                # Convert temperatures to Celsius
                if cmd == 0xd2:
                    value = (value / 2) - 20

                if self._cooked_cache.get(attr) == value:
                    continue
                self._cooked_cache[attr] = value

                for callback in callbacks:
                    await callback(attr, value)

    async def _process_data(self):
        res = self._parse_msg(self._buf)
        end = res.pop(0)
        self._buf = self._buf[end:]

        if not res:
            if len(self._buf) >= (65 * 2 + 7) * 2 and not end:
                logger.debug('%d unparsable bytes to go from %s.',
                             len(self._buf), self._geturl())
                self._buf = b''
                asyncio.ensure_future(
                    self._reconnect(delay=3),
                    loop=self._loop
                )
            return False

        msg_type = res.pop(0)
        if self._cmd:
            if self._cmd.tx and msg_type == 'ack':
                logger.debug('Read ack')
                self._cmd.tx.set()

            elif self._cmd.rx and msg_type == 'msg':
                logger.debug('Read %#x %s', res[0], res[1].hex())
                if self._cmd.rx.cmd == res[0] and \
                   self._cmd.rx.data in (None, res[1]):
                    self._cmd.rx.set()

        if msg_type == 'msg':
            for listener in self._raw_listeners:
                await listener(res)
            await self._cook_cmd(res[0], res[1])

        return True

    async def _rx_worker(self):
        while self._running:
            self._buf += await self._rx_queue.get()

            while self._buf and self._running:
                more = await self._process_data()
                if not more:
                    break

            self._rx_queue.task_done()

    async def connect(self, loop=None):
        if self._running:
            logger.debug('Already connected!')
            return

        if not loop:
            loop = asyncio.get_event_loop()

        self._loop = loop
        self._rx_queue = asyncio.Queue(loop=loop)
        self._rx_task = asyncio.ensure_future(self._rx_worker(), loop=loop)
        self._tx_queue = asyncio.Queue(loop=loop)
        self._tx_task = asyncio.ensure_future(self._tx_worker(), loop=loop)
        self._lock = asyncio.Lock(loop=loop)
        self._running = True
        await self._reconnect()

    async def _disconnect(self):
        if self._transport:
            logger.debug('Disconnecting from %s', self._geturl())
            self._transport.abort()
            self._transport = None
        self._buf = b''

    async def shutdown(self):
        async with self._lock:
            if not self._running:
                logger.debug('Already shut down!')
                return

            logger.debug('Shutting down connection to %s', self._geturl())
            self._running = False

            await self._disconnect()

            if self._rx_task:
                self._rx_task.cancel()
            if self._tx_task:
                self._tx_task.cancel()

            await asyncio.gather(self._tx_task, self._rx_task, loop=self._loop,
                                 return_exceptions=True)

    async def set_rtc(self, val: datetime):
        logger.debug('Set RTC: %s', val.ctime())

        data = pack('BBB', (val.weekday() + 2) % 7, val.hour, val.minute)
        cmd = CACommandPair(
            CACommand(self._loop, 0x35, data),
            CACommand(self._loop, 0x3c)
        )

        await self._transaction(cmd)

    async def emulate_keypress(self, key_mask: int, millis: int):
        logger.debug('Emulate keypress: %d (%d millis)', key_mask, millis)

        if not 1 <= key_mask <= 63:
            logger.error('Invalid key mask: %d', key_mask)
            return

        duration = min(max(millis, 1), 4080) * 255 // 4080
        key_status = bytearray(b'\x00' * 7)
        for key in range(6):
            if key_mask & (1 << key):
                key_status[key] = duration

        cmd_key_status = CACommandPair(
            CACommand(self._loop, 0x37, key_status),
            CACommand(self._loop, 0x3c)
        )
        await self._transaction(cmd_key_status)

    async def set_speed(self, speed: int):
        logger.debug('Set speed: %d', speed)
        cmd_set_speed = CACommandPair(
            CACommand(self._loop, 0x99, pack('B', speed))
        )
        await self._transaction(cmd_set_speed)

    async def request_version(self):
        logger.debug('Request version')
        cmd = CACommandPair(
            CACommand(self._loop, 0xa1, b''),
            CACommand(self._loop, 0xa2)
        )
        await self._transaction(cmd)

    def add_listener(self, listener):
        self._raw_listeners.add(listener)

    def remove_listener(self, listener):
        self._raw_listeners.discard(listener)

    def add_cooked_listener(self, attribute, listener):
        if attribute not in self._cooked_listeners:
            self._cooked_listeners[attribute] = set()
        self._cooked_listeners[attribute].add(listener)
        return self._cooked_cache.get(attribute)

    def remove_cooked_listener(self, attribute, listener):
        if attribute in self._cooked_listeners:
            self._cooked_listeners[attribute].discard(listener)
            if len(self._cooked_listeners[attribute]) == 0:
                del self._cooked_listeners[attribute]
