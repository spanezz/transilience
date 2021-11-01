from __future__ import annotations
import tempfile
import unittest
import stat
import os
from transilience.unittest import FileModeMixin, ActionTestMixin, LocalTestMixin, LocalMitogenTestMixin
from transilience.actions import builtin


def read_umask() -> int:
    umask = os.umask(0o777)
    os.umask(umask)
    return umask


class FileTestMixin(FileModeMixin, ActionTestMixin):
    def run_file_action(self, changed=True, failed=False, **kw):
        with self.assertUnchanged(kw["path"]):
            self.run_action(builtin.file(check=True, **kw), changed=changed, failed=failed)

        return self.run_action(builtin.file(**kw), changed=changed, failed=failed)


class TouchTests(FileTestMixin):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            act = self.run_file_action(path=testfile, state="touch", mode=0o640)

            st = os.stat(testfile)
            self.assertFileModeEqual(st, 0o640)

            self.assertEqual(act.owner, -1)
            self.assertEqual(act.group, -1)

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            act = self.run_file_action(path=testfile, state="touch", mode=0o640)

            st = os.stat(testfile)
            self.assertFileModeEqual(st, 0o640)

            self.assertEqual(act.owner, os.getuid())
            self.assertEqual(act.group, os.getgid())

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            act = self.run_file_action(path=testfile, state="touch")

            st = os.stat(testfile)
            self.assertFileModeEqual(st, 0o666 & ~umask)

            self.assertEqual(act.mode, 0o666 & ~umask)
            self.assertEqual(act.owner, -1)
            self.assertEqual(act.group, -1)

    def test_create_symbolic_perms(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            act = self.run_file_action(path=testfile, state="touch", mode="u=rw,g=r,o=")

            st = os.stat(testfile)
            self.assertFileModeEqual(st, 0o640)

            self.assertEqual(act.mode, 0o640)
            self.assertEqual(act.owner, -1)
            self.assertEqual(act.group, -1)


class TestTouchLocal(TouchTests, LocalTestMixin, unittest.TestCase):
    pass


class TestTouchMitogen(TouchTests, LocalMitogenTestMixin, unittest.TestCase):
    pass


class FileTests(FileTestMixin):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            self.run_file_action(path=testfile, state="file", mode=0o640, changed=False, failed=True)
            self.assertFalse(os.path.exists(testfile))

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            self.run_file_action(path=testfile, state="file", mode=0o640)
            st = os.stat(testfile)
            self.assertFileModeEqual(st, 0o640)

    def test_create_symbolic_perms(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o640)

            act = self.run_file_action(path=testfile, state="touch", mode="u=rX,g+w")
            st = os.stat(testfile)
            self.assertFileModeEqual(st, 0o460)
            self.assertEqual(act.mode, 0o460)

    def test_create_symbolic_perms_X(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o640)

            act = self.run_file_action(path=testfile, state="touch", mode="u=rwX", changed=False)
            st = os.stat(testfile)
            self.assertFileModeEqual(st, 0o640)
            self.assertEqual(act.mode, 0o640)


class TestFileLocal(FileTests, LocalTestMixin, unittest.TestCase):
    pass


class TestFileMitogen(FileTests, LocalMitogenTestMixin, unittest.TestCase):
    pass


class AbsentTests(FileTestMixin):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            self.run_file_action(path=testfile, state="absent", changed=False)
            self.assertFalse(os.path.exists(testfile))

    def test_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass

            self.run_file_action(path=testfile, state="absent")
            self.assertFalse(os.path.exists(testfile))

    def test_dir(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir")
            os.makedirs(testdir)
            with open(os.path.join(testdir, "testfile"), "wb"):
                pass

            self.run_file_action(path=testdir, state="absent")

            self.assertFalse(os.path.exists(testdir))


class AbsentTestsLocal(AbsentTests, LocalTestMixin, unittest.TestCase):
    pass


class AbsentTestsMitogen(AbsentTests, LocalMitogenTestMixin, unittest.TestCase):
    pass


class DirectoryTests(FileTestMixin):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            self.run_file_action(path=testdir, state="directory", mode=0o750)
            st = os.stat(testdir)
            self.assertFileModeEqual(st, 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertFileModeEqual(st, 0o750)

    def test_create_symbolic(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            self.run_file_action(path=testdir, state="directory", mode="ug=rwX,o=rX")
            st = os.stat(testdir)
            self.assertFileModeEqual(st, 0o775)
            st = os.stat(os.path.dirname(testdir))
            self.assertFileModeEqual(st, 0o775)

    def test_exists(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            os.makedirs(testdir, mode=0o700)

            self.run_file_action(path=testdir, state="directory", mode=0o750)
            st = os.stat(testdir)
            self.assertFileModeEqual(st, 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertFileModeEqual(st, 0o777 & ~umask)

    def test_exists_as_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            with open(os.path.join(workdir, "testdir1"), "wb"):
                pass

            with self.assertRaises(Exception):
                self.run_file_action(path=testdir, state="directory")

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            self.run_file_action(path=testdir, state="directory")
            st = os.stat(testdir)
            self.assertFileModeEqual(st, 0o777 & ~umask)
            st = os.stat(os.path.dirname(testdir))
            self.assertFileModeEqual(st, 0o777 & ~umask)

    def test_recurse(self):
        with tempfile.TemporaryDirectory() as workdir:
            os.makedirs(os.path.join(workdir, "testdir1", "testdir2"))
            os.chmod(os.path.join(workdir, "testdir1"), 0o700)
            os.chmod(os.path.join(workdir, "testdir1", "testdir2"), 0o777)
            with open(os.path.join(workdir, "file1"), "wt") as fd:
                os.fchmod(fd.fileno(), 0o666)
            with open(os.path.join(workdir, "testdir1", "testdir2", "file2"), "wt") as fd:
                os.fchmod(fd.fileno(), 0o777)

            self.run_file_action(path=workdir, state="directory", mode="u=rwX,g=rX,o=rX", recurse=True)

            st = os.stat(workdir)
            self.assertFileModeEqual(st, 0o755)
            st = os.stat(os.path.join(workdir, "testdir1"))
            self.assertFileModeEqual(st, 0o755)
            st = os.stat(os.path.join(workdir, "testdir1", "testdir2"))
            self.assertFileModeEqual(st, 0o755)
            st = os.stat(os.path.join(workdir, "file1"))
            self.assertFileModeEqual(st, 0o644)
            st = os.stat(os.path.join(workdir, "testdir1", "testdir2", "file2"))
            self.assertFileModeEqual(st, 0o755)


class TestDirectoryLocal(DirectoryTests, LocalTestMixin, unittest.TestCase):
    pass


class TestDirectoryMitogen(DirectoryTests, LocalMitogenTestMixin, unittest.TestCase):
    pass


class LinkTests(FileTestMixin):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            self.run_file_action(path=testfile, state="link", src=workdir)

            st = os.lstat(testfile)
            self.assertTrue(stat.S_ISLNK(st.st_mode))
            self.assertEqual(os.readlink(testfile), workdir)

            self.run_file_action(path=testfile, state="link", src=workdir, changed=False)


class TestLinkLocal(LinkTests, LocalTestMixin, unittest.TestCase):
    pass


class TestLinkMitogen(LinkTests, LocalMitogenTestMixin, unittest.TestCase):
    pass
