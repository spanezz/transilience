from __future__ import annotations
import tempfile
import unittest
import stat
import os
import mitogen.core
from transilience.unittest import LocalTestMixin
from transilience import actions


def read_umask() -> int:
    umask = os.umask(0o777)
    os.umask(umask)
    return umask


class TestTouch(LocalTestMixin, unittest.TestCase):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            res = list(self.system.run_actions([
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="touch",
                    mode=0o640,
                ),
            ]))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertEqual(res[0].owner, -1)
            self.assertEqual(res[0].group, -1)
            self.assertTrue(res[0].changed)

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            res = list(self.system.run_actions([
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="touch",
                    mode=0o640,
                ),
            ]))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertEqual(res[0].owner, os.getuid())
            self.assertEqual(res[0].group, os.getgid())
            self.assertTrue(res[0].changed)

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            res = list(self.system.run_actions([
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="touch",
                ),
            ]))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o666 & ~umask)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertEqual(res[0].mode, 0o666 & ~umask)
            self.assertEqual(res[0].owner, -1)
            self.assertEqual(res[0].group, -1)
            self.assertTrue(res[0].changed)


class TestFile(LocalTestMixin, unittest.TestCase):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            res = list(self.system.run_actions([
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="file",
                    mode=0o640,
                ),
            ]))

            self.assertFalse(os.path.exists(testfile))

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertFalse(res[0].changed)

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            res = list(self.system.run_actions([
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="file",
                    mode=0o640,
                ),
            ]))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertTrue(res[0].changed)


class TestAbsent(LocalTestMixin, unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            res = list(self.system.run_actions([
                actions.File(
                    name="Remove missing file",
                    path=testfile,
                    state="absent",
                ),
            ]))

            self.assertFalse(os.path.exists(testfile))

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertFalse(res[0].changed)

    def test_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass

            res = list(self.system.run_actions([
                actions.File(
                    name="Remove test file",
                    path=testfile,
                    state="absent",
                ),
            ]))

            self.assertFalse(os.path.exists(testfile))

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertTrue(res[0].changed)

    def test_dir(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir")
            os.makedirs(testdir)
            with open(os.path.join(testdir, "testfile"), "wb"):
                pass

            res = list(self.system.run_actions([
                actions.File(
                    name="Remove test dir",
                    path=testdir,
                    state="absent",
                ),
            ]))

            self.assertFalse(os.path.exists(testdir))

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertTrue(res[0].changed)


class TestDirectory(LocalTestMixin, unittest.TestCase):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            res = list(self.system.run_actions([
                actions.File(
                    name="Create test dir",
                    path=testdir,
                    state="directory",
                    mode=0o750,
                ),
            ]))

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertTrue(res[0].changed)

    def test_exists(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            os.makedirs(testdir, mode=0x700)

            res = list(self.system.run_actions([
                actions.File(
                    name="Create test dur",
                    path=testdir,
                    state="directory",
                    mode=0o750,
                ),
            ]))

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)
            self.assertTrue(res[0].changed)

    def test_exists_as_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            with open(os.path.join(workdir, "testdir1"), "wb"):
                pass

            with self.assertRaises(mitogen.core.CallError):
                list(self.system.run_actions([
                    actions.File(
                        name="Create test dir",
                        path=testdir,
                        state="directory",
                    ),
                ]))

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            res = list(self.system.run_actions([
                actions.File(
                    name="Create test dir",
                    path=testdir,
                    state="directory",
                ),
            ]))

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.File)

            self.assertTrue(res[0].changed)
