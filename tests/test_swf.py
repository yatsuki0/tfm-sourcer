"""The SWF reader, on small SWF files built in memory."""
import os
import shutil
import struct
import tempfile
import unittest
import zlib

from decompiler.swf import Swf


def rect(width, height):
    """Stage RECT in twips: 5-bit field size, then xmin, xmax, ymin, ymax."""
    nbits = 16
    values = [0, width * 20, 0, height * 20]
    bits = nbits
    for value in values:
        bits = bits << nbits | value
    total = 5 + 4 * nbits
    padded = (total + 7) // 8 * 8
    return (bits << (padded - total)).to_bytes(padded // 8, 'big')


def tag(code, data):
    if len(data) < 0x3F:
        return struct.pack('<H', code << 6 | len(data)) + data
    return struct.pack('<HI', code << 6 | 0x3F, len(data)) + data


def body():
    abc = struct.pack('<I', 1) + b'frame1\0' + struct.pack('<HH', 16, 46) + b'\0' * 70
    return (rect(800, 600) + bytes([0, 60]) + struct.pack('<H', 1) +
            tag(9, bytes([0x6a, 0x74, 0x95])) +
            tag(41, struct.pack('<IIBBIIQ', 3, 6, 4, 10, 0, 0, 1740614400000)) +
            tag(82, abc) +
            tag(76, struct.pack('<H', 2) + struct.pack('<H', 0) + b'Main\0' + struct.pack('<H', 3) + b'\x08\x05\0') +
            tag(1, b'') +
            tag(0, b''))


class SwfTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)

    def write(self, signature, payload, length):
        path = os.path.join(self.folder, 'test.swf')
        with open(path, 'wb') as fh:
            fh.write(signature + bytes([14]) + struct.pack('<I', length) + payload)
        return Swf(path)

    def check(self, swf):
        self.assertEqual(swf.version, 14)
        self.assertEqual((swf.width, swf.height, swf.frame_rate, swf.frame_count), (800, 600, 60, 1))
        self.assertEqual(swf.background(), '#6a7495')
        self.assertEqual(swf.symbol_classes(), {0: 'Main', 3: '\x08\x05'})
        self.assertEqual(swf.abc_versions(), [('frame1', '46.16')])
        info = swf.product_info()
        self.assertEqual((info['product'], info['version']), ('Adobe Flex', '4.10'))
        self.assertEqual(info['compiled'].strftime('%Y-%m-%d'), '2025-02-27')
        self.assertEqual(swf.tags[-1][0], 0)

    def test_uncompressed(self):
        data = body()
        swf = self.write(b'FWS', data, len(data) + 8)
        self.assertEqual(swf.signature, 'FWS')
        self.check(swf)

    def test_zlib_compressed(self):
        data = body()
        swf = self.write(b'CWS', zlib.compress(data), len(data) + 8)
        self.assertEqual(swf.signature, 'CWS')
        self.check(swf)

    def test_long_tag_header(self):
        data = body()
        swf = self.write(b'FWS', data, len(data) + 8)
        self.assertEqual(len(swf.tag(82)), 4 + 7 + 4 + 70)

    def test_not_a_swf(self):
        path = os.path.join(self.folder, 'test.swf')
        with open(path, 'wb') as fh:
            fh.write(b'PK\x03\x04' + b'\0' * 20)
        with self.assertRaises(ValueError):
            Swf(path)


if __name__ == '__main__':
    unittest.main()
