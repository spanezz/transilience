from __future__ import annotations
import contextlib
import tempfile
import unittest
import stat
import os
import mitogen.core


class LocalMixin:
    @contextlib.contextmanager
    def local_system(self):
        import mitogen
        from transilience.system import Mitogen
        broker = mitogen.master.Broker()
        router = mitogen.master.Router(broker)
        system = Mitogen("workdir", "local", router=router)
        try:
            yield system
        finally:
            broker.shutdown()


def read_umask() -> int:
    umask = os.umask(0o777)
    os.umask(umask)
    return umask


class TestTouch(LocalMixin, unittest.TestCase):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test file",
                        "path": testfile,
                        "state": "touch",
                        "mode": 0o640,
                    }
                ])

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test file",
                        "path": testfile,
                        "state": "touch",
                        "mode": 0o640,
                    }
                ])

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test file",
                        "path": testfile,
                        "state": "touch",
                    }
                ])

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o666 & ~umask)


class TestFile(LocalMixin, unittest.TestCase):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test file",
                        "path": testfile,
                        "state": "file",
                        "mode": 0o640,
                    }
                ])

            self.assertFalse(os.path.exists(testfile))

    def test_exists(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass
            os.chmod(testfile, 0o666)

            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test file",
                        "path": testfile,
                        "state": "file",
                        "mode": 0o640,
                    }
                ])

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)


class TestAbsent(LocalMixin, unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Remove missing file",
                        "path": testfile,
                        "state": "absent",
                    }
                ])

            self.assertFalse(os.path.exists(testfile))

    def test_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb"):
                pass

            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Remove test file",
                        "path": testfile,
                        "state": "absent",
                    }
                ])

            self.assertFalse(os.path.exists(testfile))

    def test_dir(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir")
            os.makedirs(testdir)
            with open(os.path.join(testdir, "testfile"), "wb"):
                pass

            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Remove test dir",
                        "path": testdir,
                        "state": "absent",
                    }
                ])

            self.assertFalse(os.path.exists(testdir))


class TestDirectory(LocalMixin, unittest.TestCase):
    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test dir",
                        "path": testdir,
                        "state": "directory",
                        "mode": 0o750,
                    }
                ])

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)

    def test_exists(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            os.makedirs(testdir, mode=0x700)

            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test dur",
                        "path": testdir,
                        "state": "directory",
                        "mode": 0o750,
                    }
                ])

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)

    def test_exists_as_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            with open(os.path.join(workdir, "testdir1"), "wb"):
                pass

            with self.local_system() as system:
                with self.assertRaises(mitogen.core.CallError):
                    system.run_actions([
                        {
                            "action": "File",
                            "name": "Create test dur",
                            "path": testdir,
                            "state": "directory",
                        }
                    ])

    def test_create_default_perms(self):
        umask = read_umask()

        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir1", "testdir2")
            with self.local_system() as system:
                system.run_actions([
                    {
                        "action": "File",
                        "name": "Create test dir",
                        "path": testdir,
                        "state": "directory",
                    }
                ])

            st = os.stat(testdir)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)
            st = os.stat(os.path.dirname(testdir))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o777 & ~umask)
