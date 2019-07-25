#
# Copyright (c) 2019 Andreas Oberritter
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

import logging
from time import sleep
import serial
from . import ComfoAirBase

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ComfoAir(ComfoAirBase):
    def __init__(self, url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._url = url
        self._port = None

    def connect(self):
        if not self._port:
            self._port = serial.serial_for_url(self._url,
                                               baudrate=self._BAUD_RATE,
                                               timeout=1)

    def send(self, cmd, data=b''):
        self.connect()
        msg = self._create_msg(cmd, data)
        logger.debug('msg=%s', msg.hex())
        self._port.reset_input_buffer()
        self._port.write(msg)
        self._port.flush()

    def _transceive_once(self, cmd, data):
        ack = False
        self.send(cmd, data)
        buf = self._port.read_until(self.__MSG_END)

        while True:
            res = self._parse_msg(buf)
            end = res.pop(0)
            logger.debug('rsp=%s', buf[:end].hex())
            buf = buf[end:]
            if not res:
                break

            if res[0] == 'ack':
                logger.debug('recv ack!')
                ack = True
            elif res[0] == 'msg':
                logger.debug('recv msg!')
                return (ack, res[1], res[2])

        return (ack, None, None)

    def transceive(self, cmd, data=b'', reply=None, expect=None):
        retries = 0
        while retries < 10:
            ack, rcmd, rdata = self._transceive_once(cmd, data)

            if ack is True and rcmd == reply and expect in (None, rdata):
                if rcmd is not None:
                    logger.debug('send ack!')
                    self._port.write(self._ack())
                return (ack, rcmd, rdata)

            sleep(0.1)
            retries += 1

        return ()
