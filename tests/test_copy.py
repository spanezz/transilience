from __future__ import annotations
import tempfile
import unittest
import stat
import os
from transilience.unittest import ActionTestMixin, LocalTestMixin, LocalMitogenTestMixin
from transilience import actions


class CopyTests(ActionTestMixin):
    def test_create_src(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            srcfile = os.path.join(workdir, "source")
            with open(srcfile, "wt") as fd:
                fd.write(payload)

            dstfile = os.path.join(workdir, "destination")

            self.system.share_file_prefix(workdir)
            self.run_action(
                actions.Copy(
                    name="Create test file",
                    src=srcfile,
                    dest=dstfile,
                    mode=0o640,
                ))

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

    def test_create_src_noop(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            srcfile = os.path.join(workdir, "source")
            with open(srcfile, "wt") as fd:
                fd.write(payload)

            dstfile = os.path.join(workdir, "destination")
            with open(dstfile, "wt") as fd:
                fd.write(payload)
                os.fchmod(fd.fileno(), 0o640)

            self.system.share_file_prefix(workdir)
            self.run_action(
                actions.Copy(
                    name="Create test file",
                    src=srcfile,
                    dest=dstfile,
                    mode=0o640,
                ), changed=False)

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

    def test_create_src_perms_only(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            srcfile = os.path.join(workdir, "source")
            with open(srcfile, "wt") as fd:
                fd.write(payload)

            dstfile = os.path.join(workdir, "destination")
            with open(dstfile, "wt") as fd:
                fd.write(payload)
                os.fchmod(fd.fileno(), 0o600)

            self.system.share_file_prefix(workdir)
            self.run_action(
                actions.Copy(
                    name="Create test file",
                    src=srcfile,
                    dest=dstfile,
                    mode=0o640,
                ))

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

    def test_create_content(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            dstfile = os.path.join(workdir, "destination")

            self.run_action(
                actions.Copy(
                    name="Create test file",
                    content=payload,
                    dest=dstfile,
                    mode=0o640,
                ))

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

    def test_create_content_noop(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"

            dstfile = os.path.join(workdir, "destination")
            with open(dstfile, "wt") as fd:
                fd.write(payload)
                os.fchmod(fd.fileno(), 0o640)

            self.run_action(
                actions.Copy(
                    name="Create test file",
                    content=payload,
                    dest=dstfile,
                    mode=0o640,
                ), changed=False)

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

    def test_create_content_perms_only(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            srcfile = os.path.join(workdir, "source")
            with open(srcfile, "wt") as fd:
                fd.write(payload)

            dstfile = os.path.join(workdir, "destination")
            with open(dstfile, "wt") as fd:
                fd.write(payload)
                os.fchmod(fd.fileno(), 0o600)

            self.system.share_file_prefix(workdir)
            self.run_action(
                actions.Copy(
                    name="Create test file",
                    content=payload,
                    dest=dstfile,
                    mode=0o640,
                ))

            with open(dstfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            st = os.stat(dstfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)


class TestCopyLocal(CopyTests, LocalTestMixin, unittest.TestCase):
    pass


class TestCopyMitogen(CopyTests, LocalMitogenTestMixin, unittest.TestCase):
    pass
