from __future__ import annotations
import tempfile
import unittest
import os
from transilience.runner import Script


class TestScript(unittest.TestCase):
    def test_sequence(self):
        script = Script()
        with tempfile.TemporaryDirectory() as workdir:
            testdir = os.path.join(workdir, "testdir")
            script.builtin.file(state="directory", path=testdir)

            testfile = os.path.join(testdir, "testfile")
            script.builtin.file(state="touch", path=testfile)

            test_payload = "test payload ♥"
            script.builtin.copy(dest=testfile, content=test_payload)

            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), test_payload)

    def test_error(self):
        script = Script()
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with self.assertRaises(Exception):
                script.builtin.file(state="file", path=testfile)
