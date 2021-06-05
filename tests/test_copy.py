from __future__ import annotations
import tempfile
import unittest
import stat
import os
from transilience.unittest import LocalTestMixin
from transilience import actions


class TestCopy(LocalTestMixin, unittest.TestCase):
    def test_create_src(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            srcfile = os.path.join(workdir, "source")
            with open(srcfile, "wt") as fd:
                fd.write(payload)

            dstfile = os.path.join(workdir, "destination")

            self.system.share_file_prefix(workdir)
            res = list(self.system.run_actions([
                actions.Copy(
                    name="Create test file",
                    src=srcfile,
                    dest=dstfile,
                    mode=0o640,
                )
            ]))

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.Copy)
            self.assertTrue(res[0].changed)

    def test_create_content(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            dstfile = os.path.join(workdir, "destination")

            res = list(self.system.run_actions([
                actions.Copy(
                    name="Create test file",
                    content=payload,
                    dest=dstfile,
                    mode=0o640,
                )
            ]))

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.Copy)
            self.assertTrue(res[0].changed)
