from __future__ import annotations
import contextlib
import tempfile
import unittest
import stat
import os
from transilience import actions


class TestMitogen(unittest.TestCase):
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

    def test_copy(self):
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
