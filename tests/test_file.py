from __future__ import annotations
import contextlib
import tempfile
import unittest
import stat
import os


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
        # Read current umask
        umask = os.umask(0o777)
        os.umask(umask)

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
