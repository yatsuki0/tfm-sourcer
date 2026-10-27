"""Before stage 1: unpack the game from a packed SWF.

The client as downloaded is a small loader. The game SWF is cut into pieces stored as
DefineBinaryData chunks; the loader joins them in a fixed, shuffled order and runs the result
with Loader.loadBytes. There is no encryption, only the shuffled order, and the loader's code
hides it behind string obfuscation that may change between versions.

The order is recovered from the data instead: the game is a compressed SWF (CWS), so its body
is one zlib stream. Starting from the chunk that begins with "CWS", only the right next chunk
continues the stream without a decompression error. A finished stream proves the order: zlib
checks its checksum, and the length must match the one in the SWF header.

The original loader and the chunk order are kept in <project>/loader/, so build.py --pack can
put a rebuilt game back into the same loader.
"""
import json
import os
import shutil
import zlib

from .swf import Swf


def find_game(swf):
    """(chunk ids in load order, game SWF bytes) if swf is a packed loader, else None."""
    chunks = swf.binary_data()
    if len(chunks) < 2:
        return None
    for first, data in chunks.items():
        if data[:3] != b'CWS' or len(data) < 8:
            continue
        expected = int.from_bytes(data[4:8], 'little') - 8
        stream = zlib.decompressobj()
        try:
            size = len(stream.decompress(data[8:]))
        except zlib.error:
            continue
        order = _extend(chunks, [first], stream, size, expected)
        if order:
            return order, b''.join(chunks[i] for i in order)
    return None


def _extend(chunks, order, stream, size, expected):
    """Depth-first: the chunk ids that complete the stream, using every chunk once."""
    if stream.eof:
        complete = len(order) == len(chunks) and size == expected and not stream.unused_data
        return order if complete else None
    for chunk_id, data in chunks.items():
        if chunk_id in order:
            continue
        attempt = stream.copy()
        try:
            added = len(attempt.decompress(data))
        except zlib.error:
            continue
        result = _extend(chunks, order + [chunk_id], attempt, size + added, expected)
        if result:
            return result
    return None


def run(cfg):
    """If cfg.swf is a packed loader, writes game.swf, loader.swf and chunks.json to cfg.loader."""
    shutil.rmtree(cfg.loader, ignore_errors=True)
    found = find_game(Swf(cfg.swf))
    if not found:
        return False
    order, game = found
    os.makedirs(cfg.loader)
    with open(os.path.join(cfg.loader, 'game.swf'), 'wb') as fh:
        fh.write(game)
    shutil.copy2(cfg.swf, os.path.join(cfg.loader, 'loader.swf'))
    with open(os.path.join(cfg.loader, 'chunks.json'), 'w', encoding='utf-8') as fh:
        json.dump({'order': order}, fh)
        fh.write('\n')
    print('%s is a packed loader: joined its %d chunks into the game SWF (%d bytes), saved in %s'
          % (os.path.basename(cfg.swf), len(order), len(game), cfg.loader))
    return True
