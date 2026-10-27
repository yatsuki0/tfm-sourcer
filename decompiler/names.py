"""The renaming scheme for obfuscated identifiers.

The obfuscator builds names from the control characters 0x01-0x08. FFDec writes them as
§\\x01§ ... §\\x07§ and §\\b§ (0x08), or with the backslash URL-encoded as %5C in file names.
Each character becomes one digit and the name gets an "_o" prefix:

    §\\x07\\b\\b\\x04§  ->  _o7884

Plain name parts are kept: §\\x07\\b_x_TransformiceFLA§ -> _o78_x_TransformiceFLA.
"""
import re

BS = chr(92)
TOKEN_RE = re.compile(r'§([^§\n]*)§')
PART_RE = re.compile(r'\\x0([1-7])|\\b|([A-Za-z0-9_]+)')
IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
PREFIX = '_o'


class Renamer:
    def __init__(self):
        self.mapping = {}

    def name(self, inner):
        """Valid identifier for the text between § marks."""
        s = inner.replace('%5C', BS)
        out, pos = [], 0
        while pos < len(s):
            m = PART_RE.match(s, pos)
            if not m:
                raise ValueError('unexpected text in token %r at %d' % (inner, pos))
            out.append(m.group(1) or ('8' if m.group(0) == BS + 'b' else m.group(2)))
            pos = m.end()
        name = PREFIX + ''.join(out)
        if not IDENT_RE.match(name):
            raise ValueError('invalid identifier %r from %r' % (name, inner))
        previous = self.mapping.setdefault(name, s)
        if previous != s:
            raise ValueError('collision: %r and %r both map to %s' % (previous, s, name))
        return name

    def text(self, text):
        return TOKEN_RE.sub(lambda m: self.name(m.group(1)), text)


def from_raw(raw):
    """Name for an identifier as stored in the SWF (real control characters)."""
    if not any('\x01' <= c <= '\x08' for c in raw):
        return raw
    return PREFIX + ''.join(str(ord(c)) if '\x01' <= c <= '\x08' else c for c in raw)
