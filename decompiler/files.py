"""Reading and writing ActionScript files without changing their line endings."""
import os
import time

# On Windows another program (often the antivirus scanning freshly exported files) can hold a
# file for a moment; opening it then fails with EACCES or EINVAL. Writes retry for a few seconds.
RETRY_DELAYS = (0.2, 0.5, 1, 2, 3)


def iter_scripts(root):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.endswith('.as'):
                yield os.path.join(dirpath, name)


def read(path):
    with open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


def write(path, text):
    def action():
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)
    retry(action, path)


def rename(path, new_path):
    retry(lambda: os.rename(path, new_path), path)


def retry(action, path):
    for delay in RETRY_DELAYS + (None,):
        try:
            return action()
        except OSError:
            if delay is None:
                raise SystemExit('Could not write %s: another program is holding it (an antivirus scan '
                                 'or an editor). Close it and run the same command again.' % path)
            time.sleep(delay)
