from __future__ import annotations
import tempfile
import unittest
import shlex
import os
from transilience.actions import builtin


class TestCommand(unittest.TestCase):
    def assertRun(self, changed=True, **kwargs):
        act = builtin.command(**kwargs)
        act.run(None)
        self.assertEqual(act.result.changed, changed)
        return act

    def test_basic(self):
        with tempfile.TemporaryDirectory() as workdir:
            payload = "♥ test content"
            testfile = os.path.join(workdir, "testfile")

            self.assertRun(argv=["touch", testfile])
            self.assertTrue(os.path.exists(testfile))

            self.assertRun(cmd="rm " + shlex.quote(testfile))
            self.assertFalse(os.path.exists(testfile))

            orig_cwd = os.getcwd()
            self.assertRun(argv=["touch", "testfile"], chdir=workdir)
            self.assertTrue(os.path.exists(testfile))
            self.assertEqual(os.getcwd(), orig_cwd)

            self.assertRun(argv=["dd", "if=/dev/stdin", "of=" + testfile], stdin=payload)
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), payload + "\n")

            self.assertRun(argv=["dd", "if=/dev/stdin", "of=" + testfile], stdin=payload.encode())
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

            self.assertRun(argv=["dd", "if=/dev/stdin", "of=" + testfile], stdin=payload, stdin_add_newline=False)
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), payload)

    def test_noop(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")

            self.assertRun(argv=["touch", testfile], creates=testfile)
            self.assertTrue(os.path.exists(testfile))

            self.assertRun(argv=["touch", testfile], creates=testfile, changed=False)
            self.assertTrue(os.path.exists(testfile))

            self.assertRun(argv=["rm", testfile], removes=testfile)
            self.assertFalse(os.path.exists(testfile))

            self.assertRun(argv=["rm", testfile], removes=testfile, changed=False)
            self.assertFalse(os.path.exists(testfile))

    def test_noop_relative(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")

            self.assertRun(argv=["touch", "testfile"], chdir=workdir, creates="testfile")
            self.assertTrue(os.path.exists(testfile))

            self.assertRun(argv=["touch", "testfile"], chdir=workdir, creates="testfile", changed=False)
            self.assertTrue(os.path.exists(testfile))

            self.assertRun(argv=["rm", "testfile"], chdir=workdir, removes="testfile")
            self.assertFalse(os.path.exists(testfile))

            self.assertRun(argv=["rm", "testfile"], chdir=workdir, removes="testfile", changed=False)
            self.assertFalse(os.path.exists(testfile))

    def test_output(self):
        payload = "♥ test content"

        res = self.assertRun(argv=["echo", payload])
        self.assertEqual(res.stdout, (payload + "\n").encode())
        self.assertEqual(res.stderr, b"")

        res = self.assertRun(argv=["dd", "if=/dev/stdin", "of=/dev/stderr", "status=none"], stdin=payload)
        self.assertEqual(res.stdout, b"")
        self.assertEqual(res.stderr, (payload + "\n").encode())
