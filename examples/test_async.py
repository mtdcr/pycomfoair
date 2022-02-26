#!/usr/bin/env python3
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
from datetime import datetime
from sys import argv, exit, stdin

from comfoair.asyncio import ComfoAir

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ComfoAirHandler():
    def __init__(self):
        self._cache = {}

    def invalidate_cache(self):
        self._cache = {}

    async def event(self, ev):
        cmd, data = ev
        if self._cache.get(cmd) == data:
            return
        self._cache[cmd] = data

        logger.info('Msg %#x: [%s]' % (cmd, data.hex()))

        cc_segments = (
            ('Sa', 'Su', 'Mo', 'Tu', 'We', 'Th', 'Fri', ':'),
            # 1-2: Hour, e.g 3, 13 or 23
            ('1ADEG', '1B', '1C', 'AUTO', 'MANUAL', 'FILTER', 'I', 'E'),
            ('2A', '2B', '2C', '2D', '2E', '2F', '2G', 'Ventilation'),
            # 3-4: Minutes, e.g 52
            ('3A', '3B', '3C', '3D', '3E', '3F', '3G', 'Extractor hood'),
            ('4A', '4B', '4C', '4D', '4E', '4F', '4G', 'Pre-heater'),
            # 5: Stufe, 1, 2, 3 or A
            ('5A', '5B', '5C', '5D', '5E', '5F', '5G', 'Frost'),
            # 6-9: Comfort temperature, e.g. 12.0°C
            ('6A', '6B', '6C', '6D', '6E', '6F', '6G', 'EWT'),
            ('7A', '7B', '7C', '7D', '7E', '7F', '7G', 'Post-heater'),
            ('8A', '8B', '8C', '8D', '8E', '8F', '8G', '.'),
            ('°', 'Bypass', '9AEF', '9G', '9D', 'House', 'Supply air', 'Exhaust air'),
        )

        ssd_chr = {
            0b0000000: ' ',
            0b0111111: '0',
            0b0000110: '1',
            0b1011011: '2',
            0b1001111: '3',
            0b1100110: '4',
            0b1101101: '5',
            0b1111101: '6',
            0b0000111: '7',
            0b1111111: '8',
            0b1101111: '9',
            0b1110111: 'A',
            0b1111100: 'B',
            0b0111001: 'C',
            0b1011110: 'D',
            0b1111001: 'E',
            0b1110001: 'F',
        }

        if cmd == 0x3c and len(cc_segments) == len(data):
            segments = []
            for pos, val in enumerate(data):
                if pos == 1:
                    digit = val & 6
                    if val & 1:
                        digit |= 0b1011001
                    assert digit in ssd_chr
                    segments.append(ssd_chr[digit])
                    offset = 3
                elif 2 <= pos <= 8:
                    digit = val & 0x7f
                    assert digit in ssd_chr
                    segments.append(ssd_chr[digit])
                    offset = 7
                elif pos == 9:
                    digit = 0
                    if val & 4:
                        digit |= 0b0110001
                    if val & 8:
                        digit |= 0b1000000
                    if val & 0x10:
                        digit |= 0b0001000
                    assert digit in ssd_chr
                    segments.append(ssd_chr[digit])
                    for i in (0, 1, 5, 6, 7):
                        if val & (1 << i):
                            segments.append(cc_segments[pos][i])
                    offset = 8
                else:
                    offset = 0

                for i in range(offset, 8):
                    if val & (1 << i):
                        segments.append(cc_segments[pos][i])

            logger.info('Segments: [%s]', '|'.join(segments))

    async def cooked_event(self, attribute, value):
        logger.info('Attribute %s: %s', attribute, value)

def main(url):
    h = ComfoAirHandler()

    logger.info('Connecting...')
    ca = ComfoAir(url)
    ca.add_listener(h.event)
    ca.add_cooked_listener(ca.AIRFLOW_EXHAUST, h.cooked_event)
    ca.add_cooked_listener(ca.FAN_SPEED_MODE, h.cooked_event)
    ca.add_cooked_listener(ca.TEMP_OUTSIDE, h.cooked_event)

    def read_from_stdin():
        c = stdin.readline().strip()
        try:
            n = int(c)
        except ValueError:
            if not c:
                pass
            elif c in ('a', 'add'):
                ca.add_listener(h.event)
            elif c in ('c', 'connect'):
                asyncio.ensure_future(ca.connect())
            elif c in ('i', 'invalidate'):
                h.invalidate_cache()
            elif c in ('k0', 'k1', 'k2', 'k3', 'k4'):
                asyncio.ensure_future(ca.emulate_keypress(1 << int(c[1]), 100))
            elif c in ('q', 'quit'):
                exit(0)
            elif c in ('r', 'remove'):
                ca.remove_listener(h.event)
            elif c in ('s', 'shutdown'):
                asyncio.ensure_future(ca.shutdown())
            elif c in ('t', 'time'):
                asyncio.ensure_future(ca.set_rtc(datetime.now()))
            elif c in ('v', 'version'):
                asyncio.ensure_future(ca.request_version())
            else:
                from IPython import embed
                embed()
        else:
            if n >= 1 and n <= 4:
                asyncio.ensure_future(ca.set_speed(n))

    loop = asyncio.get_event_loop()
    loop.add_reader(stdin, read_from_stdin)
    loop.run_until_complete(ca.connect())
    loop.run_forever()
    loop.close()


if __name__ == '__main__':
    if len(argv) != 2:
        print('usage: %s socket://127.0.0.1:51944\n' % argv[0] +
              '   or: %s /dev/ttyS0' % argv[0])
        exit(1)

    main(argv[1])
    exit(0)
