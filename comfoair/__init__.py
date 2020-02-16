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

from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ComfoAirBase:
    _BAUD_RATE = 9600

    __MSG_ESC = b'\x07'
    __MSG_START = __MSG_ESC + b'\xF0'
    __MSG_END = __MSG_ESC + b'\x0F'
    __MSG_ACK = __MSG_ESC + b'\xF3'

    __PATTERN = re.compile(
        #b'(?P<start>%s)' % __MSG_START +
        __MSG_START +
        b'(?P<cmd>\x00[%s])' %
        (
            b'\x02\x04\x0C\x0E' +
            b'\x10\x12\x14\x1A' +
            b'\x38\x3C\x3E\x40' +
            b'\x66\x68\x6A' +
            b'\x70\x72\x74' +
            b'\x98\x9C\x9E' +
            b'\xA2\xAA\xCA\xCE' +
            b'\xD2\xD6\xDA\xDE' +
            b'\xE0\xE2\xE6\xEA\xEC'
        ) +
        b'(?P<length>[\x00-\x40])' +
        b'(?P<data>(?:[^%s]|%s){0,64})' % (__MSG_ESC, __MSG_ESC * 2) +
        b'(?P<cs>(?:[^%s]|%s))' % (__MSG_ESC, __MSG_ESC * 2) +
        #b'(?P<end>%s)' % __MSG_END +
        __MSG_END +
        b'|' +
        b'(?P<ack>%s)' % __MSG_ACK,
        re.DOTALL)

    @dataclass(frozen=True)
    class Attribute:
        cmd: int
        offset: int
        size: int

    AIRFLOW_EXHAUST = Attribute(0xCE, 6 * 8, 8)
    AIRFLOW_SUPPLY = Attribute(0xCE, 7 * 8, 8)
    FAN_SPEED_MODE = Attribute(0xCE, 8 * 8, 8)
    TEMP_COMFORT = Attribute(0xD2, 0 * 8, 8)
    TEMP_OUTSIDE = Attribute(0xD2, 1 * 8, 8)
    TEMP_SUPPLY = Attribute(0xD2, 2 * 8, 8)
    TEMP_RETURN = Attribute(0xD2, 3 * 8, 8)
    TEMP_EXHAUST = Attribute(0xD2, 4 * 8, 8)

    @staticmethod
    def _checksum(buf):
        return (sum(buf) + 173) & 0xff

    @staticmethod
    def _escape(msg):
        return msg.replace(ComfoAirBase.__MSG_ESC, ComfoAirBase.__MSG_ESC * 2)

    @staticmethod
    def _unescape(msg):
        return msg.replace(ComfoAirBase.__MSG_ESC * 2, ComfoAirBase.__MSG_ESC)

    @staticmethod
    def _ack():
        return ComfoAirBase.__MSG_ACK

    @staticmethod
    def _create_msg(cmd, data=b''):
        from struct import pack
        payload = pack('>H', cmd)
        payload += pack('B', len(data))
        payload += ComfoAirBase._escape(data)
        checksum = ComfoAirBase._checksum(payload)
        payload += ComfoAirBase._escape(pack('B', checksum))
        return ComfoAirBase.__MSG_START + payload + ComfoAirBase.__MSG_END

    @staticmethod
    def _parse_msg(buf):
        start = 0
        end = 0

        for match in ComfoAirBase.__PATTERN.finditer(buf):
            if match.start() > start:
                logger.debug('Skipped %d bytes at offset %d: [%s]',
                             match.start() - start, start,
                             buf[start:match.start()].hex())

            if match.group('ack'):
                return [match.end(), 'ack']

            data = ComfoAirBase._unescape(match.group('data'))
            length = match.group('length')[0]
            if len(data) == length:
                checksum = ComfoAirBase._unescape(match.group('cs'))[0]
                payload = match.group('cmd') + match.group('length') + data
                if ComfoAirBase._checksum(payload) == checksum:
                    cmd = int.from_bytes(match.group('cmd'), 'big')
                    return [match.end(), 'msg', cmd, data]

            if len(data) < length and \
               len(buf) - match.start() < (length * 2) + 8:
                break

            logger.debug('Cannot parse %d bytes at offset %d: [%s]',
                         len(match.group(0)), match.start(),
                         match.group(0).hex())

            start = match.start()
            assert match.end() > end
            end = match.end()

        return [end]
