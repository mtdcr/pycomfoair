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
from os.path import realpath
from sys import argv, exit
from comfoair import ComfoAirBase

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_create_parse(tag: int, value: bytes, expect: bytes) -> None:
    msg = ComfoAirBase._create_msg(tag, value)
    assert msg == expect

    parsed = ComfoAirBase._parse_msg(msg)
    assert parsed == [len(msg), 'msg', tag, value]


def test_create_parse_hex(tag: int, value: str, expect: str) -> None:
    test_create_parse(tag, bytes.fromhex(value), bytes.fromhex(expect))


def test_bytes(buf: bytes):
    n = 0
    while buf:
        res = ComfoAirBase._parse_msg(buf)
        logger.debug(res)
        end = res.pop(0)
        if end == 0:
            logger.debug('remainder: %s', buf.hex())
            break
        buf = buf[end:]
        n += 1

    logger.debug("matched %d times", n)


def test_static() -> int:
    value = 'c073866d0606000000e2'
    expect = '07f0003c0ac073866d0606000000e20707070f'
    test_create_parse_hex(0x3c, value, expect)
    return 0


if __name__ == '__main__':
    if len(argv) == 1:
        exit(test_static())

    for arg in argv[1:]:
        with open(realpath(arg), 'rb') as f:
            test_bytes(f.read())
