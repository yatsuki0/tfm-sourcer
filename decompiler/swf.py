"""Minimal SWF reader: header, tags, SymbolClass, ProductInfo and ABC versions.

Handles uncompressed (FWS), zlib (CWS) and LZMA (ZWS) files.
"""
import collections
import datetime
import lzma
import struct
import zlib

TAG_NAMES = {0: 'End', 1: 'ShowFrame', 9: 'SetBackgroundColor', 41: 'ProductInfo', 43: 'FrameLabel',
             56: 'ExportAssets', 63: 'DebugID', 64: 'EnableDebugger2', 65: 'ScriptLimits',
             69: 'FileAttributes', 73: 'DefineFontAlignZones', 75: 'DefineFont3', 76: 'SymbolClass',
             77: 'Metadata', 82: 'DoABC', 86: 'DefineSceneAndFrameLabelData', 87: 'DefineBinaryData',
             88: 'DefineFontName', 91: 'DefineFont4'}

PRODUCTS = {0: 'unknown', 1: 'Macromedia Flex for J2EE', 2: 'Macromedia Flex for .NET', 3: 'Adobe Flex'}


class Swf:
    def __init__(self, path):
        with open(path, 'rb') as fh:
            data = fh.read()
        self.file_size = len(data)
        self.signature = data[:3].decode('ascii')
        self.version = data[3]
        if self.signature == 'FWS':
            body = data[8:]
        elif self.signature == 'CWS':
            body = zlib.decompress(data[8:])
        elif self.signature == 'ZWS':
            # LZMA SWF: compressed length (4), LZMA properties (5), raw stream without end marker.
            raw_len = struct.unpack_from('<I', data, 4)[0] - 8
            header = data[12:17] + b'\xff' * 8
            body = lzma.LZMADecompressor(lzma.FORMAT_ALONE).decompress(header + data[17:], raw_len)
        else:
            raise ValueError('%s is not a SWF file' % path)
        self.body = body
        nbits = body[0] >> 3
        rect_bytes = (5 + 4 * nbits + 7) // 8
        # Stage RECT: 5-bit field size, then xmin, xmax, ymin, ymax in twips.
        bits = int.from_bytes(body[:rect_bytes], 'big')
        total = rect_bytes * 8
        xmin, xmax, ymin, ymax = [(bits >> (total - 5 - nbits * (i + 1))) & ((1 << nbits) - 1) for i in range(4)]
        self.width = (xmax - xmin) // 20
        self.height = (ymax - ymin) // 20
        self.frame_rate = body[rect_bytes + 1]
        self.frame_count = struct.unpack_from('<H', body, rect_bytes + 2)[0]
        self.tags = list(self._read_tags(rect_bytes + 4))

    def _read_tags(self, pos):
        body = self.body
        while pos < len(body):
            code_len = struct.unpack_from('<H', body, pos)[0]
            code, length = code_len >> 6, code_len & 0x3F
            pos += 2
            if length == 0x3F:
                length = struct.unpack_from('<I', body, pos)[0]
                pos += 4
            yield code, body[pos:pos + length]
            if code == 0:
                return
            pos += length

    def tag(self, code):
        return next((data for c, data in self.tags if c == code), None)

    def background(self):
        data = self.tag(9)
        return '#%02x%02x%02x' % tuple(data[:3]) if data else None

    def symbol_classes(self):
        """{character id: raw class name}. Id 0 is the document (main) class."""
        data = self.tag(76)
        result = {}
        if data:
            count = struct.unpack_from('<H', data, 0)[0]
            pos = 2
            for _ in range(count):
                char_id = struct.unpack_from('<H', data, pos)[0]
                end = data.index(b'\0', pos + 2)
                result[char_id] = data[pos + 2:end].decode('utf-8')
                pos = end + 1
        return result

    def product_info(self):
        data = self.tag(41)
        if not data:
            return None
        product, edition, major, minor, build_lo, build_hi, date = struct.unpack('<IIBBIIQ', data[:26])
        return {'product': PRODUCTS.get(product, str(product)), 'edition': edition,
                'version': '%d.%d' % (major, minor), 'build': build_lo | build_hi << 32,
                'compiled': datetime.datetime.fromtimestamp(date / 1000, datetime.timezone.utc)}

    def abc_versions(self):
        """[(name, 'major.minor')] for each DoABC tag."""
        result = []
        for code, data in self.tags:
            if code == 82:
                end = data.index(b'\0', 4)
                minor, major = struct.unpack_from('<HH', data, end + 1)
                result.append((data[4:end].decode('utf-8'), '%d.%d' % (major, minor)))
        return result

    def tag_summary(self):
        counts = collections.Counter()
        sizes = collections.Counter()
        for code, data in self.tags:
            counts[code] += 1
            sizes[code] += len(data)
        return [(code, TAG_NAMES.get(code, '?'), counts[code], size) for code, size in sizes.most_common()]
