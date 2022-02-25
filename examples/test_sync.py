#!/usr/bin/env python3
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
from struct import pack
from sys import argv, exit

from comfoair.sync import ComfoAir

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def main(url, level):
    logger.info('Connecting...')
    ca = ComfoAir(url)
    ca.connect()

    if not ca.transceive(0x9b, b'\x03', reply=0x9c, expect=b'\x03'):
        print('Failed to switch to PC mode!')
    elif not ca.transceive(0x99, pack('B', level)):
        print('Failed to set fan speed!')
    elif not ca.transceive(0x9b, b'\x00', reply=0x9c, expect=b'\x02'):
        print('Failed to switch to CC-Ease mode!')
    else:
        exit(0)

    exit(1)


if __name__ == '__main__':
    if len(argv) != 3:
        print('usage: %s socket://127.0.0.1:51944 <level>\n' % argv[0] +
              '   or: %s /dev/ttyS0 <level>' % argv[0])
        exit(1)

    level = int(argv[2])
    if level >= 0 and level <= 4:
        main(argv[1], level)
