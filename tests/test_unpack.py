"""Packed SWFs: unpacking the game from a loader, and build.py --pack putting it back."""
import json
import os
import random
import shutil
import struct
import tempfile
import unittest
import zlib

import build
from decompiler import unpack
from decompiler.swf import Swf
from tests.test_swf import body as plain_body, rect, tag

WORDS = ['stage', 'mouse', 'cheese', 'hole', 'shaman', 'map', 'jump', 'run', 'room', 'tribe']


def fake_game(seed):
    """A compressed SWF whose code tag is varied text, so its zlib stream is not trivial."""
    rng = random.Random(seed)
    code = ' '.join(rng.choice(WORDS) + str(rng.randrange(1000)) for _ in range(12000)).encode()
    body = rect(800, 600) + bytes([0, 60]) + struct.pack('<H', 1) + tag(82, code) + tag(1, b'') + tag(0, b'')
    return b'CWS' + bytes([14]) + struct.pack('<I', 8 + len(body)) + zlib.compress(body)


def split(data, count):
    size = len(data) // count
    return [data[i * size:(i + 1) * size] for i in range(count - 1)] + [data[(count - 1) * size:]]


def binary_data_tag(chunk_id, data):
    payload = struct.pack('<HI', chunk_id, 0) + data
    return struct.pack('<HI', 87 << 6 | 0x3F, len(payload)) + payload


ORDER = [12, 10, 14, 11, 13]


def fake_loader(game):
    """An uncompressed loader SWF holding the game's pieces as chunks, stored by id, joined in ORDER."""
    pieces = dict(zip(ORDER, split(game, len(ORDER))))
    body = (rect(800, 600) + bytes([0, 36]) + struct.pack('<H', 1) + tag(9, bytes([0x6a, 0x74, 0x95])) +
            b''.join(binary_data_tag(i, pieces[i]) for i in sorted(pieces)) + tag(1, b'') + tag(0, b''))
    return b'FWS' + bytes([14]) + struct.pack('<I', 8 + len(body)) + body


class UnpackTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)

    def swf(self, data, name='test.swf'):
        path = os.path.join(self.folder, name)
        with open(path, 'wb') as fh:
            fh.write(data)
        return path

    def test_finds_the_order_from_the_data(self):
        game = fake_game(1)
        self.assertEqual(unpack.find_game(Swf(self.swf(fake_loader(game)))), (ORDER, game))

    def test_plain_swf_is_not_packed(self):
        data = plain_body()
        self.assertIsNone(unpack.find_game(Swf(self.swf(b'FWS' + bytes([14]) + struct.pack('<I', len(data) + 8) + data))))

    def test_missing_chunk_is_not_a_game(self):
        game = fake_game(1)
        pieces = split(game, len(ORDER))
        body = (rect(800, 600) + bytes([0, 36]) + struct.pack('<H', 1) +
                binary_data_tag(1, pieces[0]) + binary_data_tag(2, pieces[2]) + tag(0, b''))
        data = b'FWS' + bytes([14]) + struct.pack('<I', 8 + len(body)) + body
        self.assertIsNone(unpack.find_game(Swf(self.swf(data))))


class PackTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)

    def test_repacking_the_same_game_gives_the_same_file(self):
        game = fake_game(1)
        loader = fake_loader(game)
        pieces = dict(zip(ORDER, split(game, len(ORDER))))
        self.assertEqual(build.replace_binary_data(loader, pieces), loader)

    def test_pack_puts_a_new_game_into_the_loader(self):
        loader_dir = os.path.join(self.folder, 'loader')
        os.makedirs(loader_dir)
        with open(os.path.join(loader_dir, 'loader.swf'), 'wb') as fh:
            fh.write(fake_loader(fake_game(1)))
        with open(os.path.join(loader_dir, 'chunks.json'), 'w') as fh:
            json.dump({'order': ORDER}, fh)
        new_game = fake_game(2)
        game_path = os.path.join(self.folder, 'game.swf')
        with open(game_path, 'wb') as fh:
            fh.write(new_game)
        output = os.path.join(self.folder, 'packed', 'Game.swf')
        build.pack(loader_dir, game_path, output)
        packed = Swf(output)
        self.assertEqual(packed.frame_rate, 36)
        self.assertEqual(unpack.find_game(packed), (ORDER, new_game))

    def test_compressed_loader_stays_compressed(self):
        loader = fake_loader(fake_game(1))
        compressed = b'CWS' + loader[3:8] + zlib.compress(loader[8:])
        result = build.replace_binary_data(compressed, {})
        self.assertEqual(result[:3], b'CWS')
        self.assertEqual(zlib.decompress(result[8:]), loader[8:])

    def test_unknown_chunk_id_stops(self):
        with self.assertRaises(SystemExit):
            build.replace_binary_data(fake_loader(fake_game(1)), {99: b''})


if __name__ == '__main__':
    unittest.main()
