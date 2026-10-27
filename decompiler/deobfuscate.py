"""Stage 2: rename the obfuscated §...§ identifiers in code, file names and [Embed] paths."""
import os

from .files import read, rename, write
from .names import Renamer


def run(cfg):
    renamer = Renamer()
    edited = renamed = 0
    # Bottom-up so renaming a folder doesn't invalidate paths still to visit.
    for dirpath, dirnames, filenames in os.walk(cfg.src, topdown=False):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if name.endswith('.as'):
                text = read(path)
                new = renamer.text(text)
                if new != text:
                    write(path, new)
                    edited += 1
            new_name = renamer.text(name)
            if new_name != name:
                rename(path, os.path.join(dirpath, new_name))
                renamed += 1
        for name in dirnames:
            new_name = renamer.text(name)
            if new_name != name:
                rename(os.path.join(dirpath, name), os.path.join(dirpath, new_name))
                renamed += 1
    print('Renamed %d identifiers: %d files edited, %d paths renamed' % (len(renamer.mapping), edited, renamed))
