from __future__ import annotations
import unittest
import tempfile
import zipfile
import os
import io
from transilience.fileasset import FileAsset, LocalFileAsset, ZipFileAsset


class TestFileAssets(unittest.TestCase):
    def assertRead(self, fa: FileAsset, expected: bytes):
        with fa.open() as fd:
            self.assertEqual(fd.read(), expected)

        with io.BytesIO() as fd:
            fa.copy_to(fd)
            self.assertEqual(fd.getvalue(), expected)

    def test_local_small(self):
        with tempfile.NamedTemporaryFile("w+b") as tf:
            test_content = "test content ♥".encode()
            tf.write(test_content)
            tf.flush()

            a = LocalFileAsset(tf.name)
            self.assertEqual(a.sha1sum(), "e5a07c60318532612d09da40e729bccf71018ed7")
            self.assertEqual(a.cached, test_content)
            self.assertRead(a, test_content)

            a1 = FileAsset.deserialize(a.serialize())
            self.assertEqual(a1.cached, a.cached)
            self.assertEqual(a1.path, a.path)

    def test_local_big(self):
        with tempfile.NamedTemporaryFile("w+b") as tf:
            # One megabyte file asset
            os.ftruncate(tf.fileno(), 1024*1024)

            a = LocalFileAsset(tf.name)
            self.assertEqual(a.sha1sum(), "3b71f43ff30f4b15b5cd85dd9e95ebc7e84eb5a3")
            self.assertIsNone(a.cached)
            self.assertRead(a, bytes(1024*1024))

            a1 = FileAsset.deserialize(a.serialize())
            self.assertEqual(a1.cached, a.cached)
            self.assertEqual(a1.path, a.path)

    def test_zip(self):
        test_content = "test content ♥".encode()
        with tempfile.NamedTemporaryFile("w+b") as tf:
            with zipfile.ZipFile(tf, mode='w') as zf:
                zf.writestr("dir/testfile", test_content)

            a = ZipFileAsset(tf.name, "dir/testfile")
            self.assertEqual(a.sha1sum(), "e5a07c60318532612d09da40e729bccf71018ed7")
            self.assertEqual(a.cached, test_content)
            self.assertRead(a, test_content)

            a1 = FileAsset.deserialize(a.serialize())
            self.assertEqual(a1.cached, a.cached)
            self.assertEqual(a1.path, a.path)

    def test_zip_big(self):
        with tempfile.NamedTemporaryFile("w+b") as tf:
            with zipfile.ZipFile(tf, mode='w') as zf:
                zf.writestr("dir/testfile", bytes(1024*1024))

            a = ZipFileAsset(tf.name, "dir/testfile")
            self.assertEqual(a.sha1sum(), "3b71f43ff30f4b15b5cd85dd9e95ebc7e84eb5a3")
            self.assertIsNone(a.cached)
            self.assertRead(a, bytes(1024*1024))

            a1 = FileAsset.deserialize(a.serialize())
            self.assertEqual(a1.cached, a.cached)
            self.assertEqual(a1.path, a.path)
