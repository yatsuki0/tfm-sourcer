"""The setup download helper, on local file:// URLs, so no network is needed."""
import os
import pathlib
import shutil
import tempfile
import unittest

from decompiler.setup_sdk import download, progress


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_downloads_and_leaves_no_part_file(self):
        source = os.path.join(self.dir, 'source.bin')
        data = os.urandom(200000)
        with open(source, 'wb') as fh:
            fh.write(data)
        target = os.path.join(self.dir, 'target.bin')
        download(pathlib.Path(source).as_uri(), target, quiet=True)
        with open(target, 'rb') as fh:
            self.assertEqual(fh.read(), data)
        self.assertFalse(os.path.exists(target + '.part'))

    def test_failed_download_leaves_no_target(self):
        target = os.path.join(self.dir, 'target.bin')
        missing = pathlib.Path(os.path.join(self.dir, 'missing.bin')).as_uri()
        with self.assertRaises(OSError):
            download(missing, target, quiet=True)
        self.assertFalse(os.path.exists(target))


class ProgressTest(unittest.TestCase):
    def test_with_known_size(self):
        self.assertEqual(progress(35 * 1024 * 1024, 70 * 1024 * 1024), '35.0 of 70.0 MB (50%)')

    def test_with_unknown_size(self):
        self.assertEqual(progress(3 * 1024 * 1024, 0), '3.0 MB')


if __name__ == '__main__':
    unittest.main()
