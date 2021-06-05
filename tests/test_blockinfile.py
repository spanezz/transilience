from __future__ import annotations
from typing import List
import tempfile
import unittest
import stat
import os
from transilience.unittest import LocalTestMixin
from transilience import actions


def read_umask() -> int:
    umask = os.umask(0o777)
    os.umask(umask)
    return umask


class TestBlockInFile(LocalTestMixin, unittest.TestCase):
    def assertBlockInFileChanged(self, orig: List[str], expected: List[str], **kw):
        kw.setdefault("block", "")

        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "wb") as fd:
                for line in orig:
                    fd.write(line.encode())

            action = actions.BlockInFile(
                name="Edit test file",
                path=testfile,
                **kw
            )
            action.run(None)
            self.assertTrue(action.changed)

            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), "".join(expected))

    def test_missing_noop(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            res = list(self.system.run_actions([
                actions.BlockInFile(
                    name="Create test file",
                    path=testfile,
                    mode=0o640,
                    block="test",
                ),
            ]))

            self.assertFalse(os.path.exists(testfile))
            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.BlockInFile)
            self.assertEqual(res[0].owner, -1)
            self.assertEqual(res[0].group, -1)
            self.assertFalse(res[0].changed)

    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            res = list(self.system.run_actions([
                actions.BlockInFile(
                    name="Create test file",
                    path=testfile,
                    mode=0o640,
                    create=True,
                    block="test",
                ),
            ]))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(len(res), 1)
            self.assertIsInstance(res[0], actions.BlockInFile)
            self.assertEqual(res[0].owner, -1)
            self.assertEqual(res[0].group, -1)
            self.assertTrue(res[0].changed)

            with open(testfile, "rb") as fd:
                self.assertEqual(fd.readlines(), [
                    b"# BEGIN ANSIBLE MANAGED BLOCK\n",
                    b"test\n",
                    b"# END ANSIBLE MANAGED BLOCK\n",
                ])

    def test_edit_existing(self):
        self.maxDiff = None

        begin = "# BEGIN ANSIBLE MANAGED BLOCK"
        end = "# END ANSIBLE MANAGED BLOCK"

        def lines(*lns) -> List[str]:
            res = []
            for line in lns:
                res.append(line.strip() + "\n")
            return res

        self.assertBlockInFileChanged(
                lines("line0", begin, "line1", end, "line2"),
                lines("line0", begin, "test", "test1", end, "line2"),
                block="test\ntest1\n")

        self.assertBlockInFileChanged(
                lines("line0", begin, "line1", end, "line2"),
                lines("line0", "line2"))

        self.assertBlockInFileChanged(
                lines(begin, "line1", end),
                lines(begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFileChanged(
                lines(begin, "line1", end),
                [])

        self.assertBlockInFileChanged(
                lines(begin, end),
                lines(begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFileChanged(
                lines(begin, end),
                [])

        # An open-ended block is condered to go on until the end of the file
        self.assertBlockInFileChanged(
                lines(end, "line1", begin),
                lines(end, "line1", begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFileChanged(
                lines(end, "line1", begin),
                lines(end, "line1"))

        self.assertBlockInFileChanged(
                lines(end, "line1", begin, "openended"),
                lines(end, "line1", begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFileChanged(
                lines(end, "line1", begin, "openended"),
                lines(end, "line1"))

        # If multiple begin markers are found before an end marker, the first
        # is considered as the valid one
        self.assertBlockInFileChanged(
                lines(end, "line1", begin, begin, "line", end),
                lines(end, "line1", begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFileChanged(
                lines(end, "line1", begin, begin, "line", end),
                lines(end, "line1"))

        # If multiple marker pairs exist, only the last one is considered
        self.assertBlockInFileChanged(
                lines(begin, "block1", end, "out1", begin, "block2", end, "out2"),
                lines(begin, "block1", end, "out1", begin, "test", end, "out2"),
                block="test")

        self.assertBlockInFileChanged(
                lines(begin, "block1", end, "out1", begin, "block2", end, "out2"),
                lines(begin, "block1", end, "out1", "out2"))
