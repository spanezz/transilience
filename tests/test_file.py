from __future__ import annotations
import tempfile
import unittest
import stat
import os
from transilience.unittest import ActionTestMixin, LocalTestMixin, LocalMitogenTestMixin
from transilience import actions


def read_umask() -> int:
    umask = os.umask(0o777)
    os.umask(umask)
    return umask


class TouchTests(ActionTestMixin):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            act = self.run_action(
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="touch",
                    mode=0o640,
                ))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(act.owner, -1)
            self.assertEqual(act.group, -1)

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            act = self.run_action(
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="touch",
                    mode=0o640,
                ))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(act.owner, os.getuid())
            self.assertEqual(act.group, os.getgid())

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            act = self.run_action(
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="touch",
                ))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o666 & ~umask)

            self.assertEqual(act.mode, 0o666 & ~umask)
            self.assertEqual(act.owner, -1)
            self.assertEqual(act.group, -1)


class TestTouchLocal(TouchTests, LocalTestMixin, unittest.TestCase):
    pass


class TestTouchMitogen(TouchTests, LocalMitogenTestMixin, unittest.TestCase):
    pass


class FileTests(ActionTestMixin):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            self.run_action(
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="file",
                    mode=0o640,
                ), changed=False)

            self.assertFalse(os.path.exists(testfile))

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            self.run_action(
                actions.File(
                    name="Create test file",
                    path=testfile,
                    state="file",
                    mode=0o640,
                ))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)


class TestFileLocal(FileTests, LocalTestMixin, unittest.TestCase):
    pass


class TestFileMitogen(FileTests, LocalMitogenTestMixin, unittest.TestCase):
    pass


class AbsentTests(ActionTestMixin):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            self.run_action(
                actions.File(
                    name="Remove missing file",
                    path=testfile,
                    state="absent",
                ), changed=False)

            self.assertFalse(os.path.exists(testfile))

    def test_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass

            self.run_action(
                actions.File(
                    name="Remove test file",
                    path=testfile,
                    state="absent",
                ))

            self.assertFalse(os.path.exists(testfile))

    def test_dir(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir")
            os.makedirs(testdir)
            with open(os.path.join(testdir, "testfile"), "wb"):
                pass

            self.run_action(
                actions.File(
                    name="Remove test dir",
                    path=testdir,
                    state="absent",
                ))

            self.assertFalse(os.path.exists(testdir))


class AbsentTestsLocal(AbsentTests, LocalTestMixin, unittest.TestCase):
    pass


class AbsentTestsMitogen(AbsentTests, LocalMitogenTestMixin, unittest.TestCase):
    pass


class DirectoryTests(ActionTestMixin):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            self.run_action(
                actions.File(
                    name="Create test dir",
                    path=testdir,
                    state="directory",
                    mode=0o750,
                ))

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)

    def test_exists(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            os.makedirs(testdir, mode=0x700)

            self.run_action(
                actions.File(
                    name="Create test dur",
                    path=testdir,
                    state="directory",
                    mode=0o750,
                ))

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)

    def test_exists_as_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            with open(os.path.join(workdir, "testdir1"), "wb"):
                pass

            with self.assertRaises(Exception):
                self.run_action(
                    actions.File(
                        name="Create test dir",
                        path=testdir,
                        state="directory",
                    ))

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            self.run_action(
                actions.File(
                    name="Create test dir",
                    path=testdir,
                    state="directory",
                ))

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)


class TestDirectoryLocal(DirectoryTests, LocalTestMixin, unittest.TestCase):
    pass


class TestDirectoryMitogen(DirectoryTests, LocalMitogenTestMixin, unittest.TestCase):
    pass
