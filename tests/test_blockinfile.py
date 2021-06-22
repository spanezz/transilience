from __future__ import annotations
from typing import List, Optional
from contextlib import contextmanager
import tempfile
import unittest
import stat
import os
from transilience.unittest import ActionTestMixin, LocalTestMixin, LocalMitogenTestMixin
from transilience.actions import builtin, ResultState


def read_umask() -> int:
    umask = os.umask(0o777)
    os.umask(umask)
    return umask


class BlockInFileTests(ActionTestMixin, LocalTestMixin, unittest.TestCase):
    @contextmanager
    def testfile(self, orig: Optional[List[str]] = None):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            if orig is not None:
                with open(testfile, "wb") as fd:
                    for line in orig:
                        fd.write(line.encode())
            else:
                if os.path.exists(testfile):
                    os.unlink(testfile)

            yield testfile

    def assertBlockInFile(self, orig: Optional[List[str]] = None, expected: Optional[List[str]] = None, **kw):
        kw.setdefault("block", "")

        # Test with check = False
        with self.testfile(orig) as testfile:
            action = builtin.blockinfile(
                path=testfile,
                **kw
            )
            action.run(None)

            if expected is not None:
                self.assertEqual(action.result.state, ResultState.CHANGED)

                with open(testfile, "rt") as infd:
                    self.assertEqual(infd.read(), "".join(expected))
            else:
                self.assertEqual(action.result.state, ResultState.NOOP)

                with open(testfile, "rt") as infd:
                    self.assertEqual(infd.read(), "".join(orig))

        # Test with check = True
        with self.testfile(orig) as testfile:
            try:
                orig_stat = os.stat(testfile)
            except FileNotFoundError:
                orig_stat = None

            action = builtin.blockinfile(
                path=testfile,
                check=True,
                **kw
            )
            action.run(None)

            if expected is not None:
                self.assertEqual(action.result.state, ResultState.CHANGED)
            else:
                self.assertEqual(action.result.state, ResultState.NOOP)

            if orig_stat is None:
                self.assertFalse(os.path.exists(testfile))
            else:
                self.assertEqual(os.stat(testfile), orig_stat)
                with open(testfile, "rt") as infd:
                    self.assertEqual(infd.read(), "".join(orig))

    def test_missing_noop(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            act = self.run_action(
                builtin.blockinfile(
                    path=testfile,
                    mode=0o640,
                    block="test",
                ), changed=False)

            self.assertFalse(os.path.exists(testfile))
            self.assertEqual(act.owner, -1)
            self.assertEqual(act.group, -1)

    def test_create(self):
        with tempfile.TemporaryDirectory() as workdir:
            testfile = os.path.join(workdir, "testfile")
            act = self.run_action(
                builtin.blockinfile(
                    path=testfile,
                    mode=0o640,
                    create=True,
                    block="test",
                ))

            st = os.stat(testfile)
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)

            self.assertEqual(act.owner, -1)
            self.assertEqual(act.group, -1)

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

        self.assertBlockInFile(
                None,
                lines(begin, "test", "test1", end),
                block="test\ntest1\n",
                create=True)

        self.assertBlockInFile(
                lines("line0", begin, "line1", end, "line2"),
                lines("line0", begin, "test", "test1", end, "line2"),
                block="test\ntest1\n")

        self.assertBlockInFile(
                lines("line0", begin, "line1", end, "line2"),
                lines("line0", "line2"))

        self.assertBlockInFile(
                lines(begin, "line1", end),
                lines(begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFile(
                lines(begin, "line1", end),
                [])

        self.assertBlockInFile(
                lines(begin, end),
                lines(begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFile(
                lines(begin, end),
                [])

        # An open-ended block is condered to go on until the end of the file
        self.assertBlockInFile(
                lines(end, "line1", begin),
                lines(end, "line1", begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFile(
                lines(end, "line1", begin),
                lines(end, "line1"))

        self.assertBlockInFile(
                lines(end, "line1", begin, "openended"),
                lines(end, "line1", begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFile(
                lines(end, "line1", begin, "openended"),
                lines(end, "line1"))

        # If multiple begin markers are found before an end marker, the first
        # is considered as the valid one
        self.assertBlockInFile(
                lines(end, "line1", begin, begin, "line", end),
                lines(end, "line1", begin, "test", "test1", end),
                block="test\ntest1\n")

        self.assertBlockInFile(
                lines(end, "line1", begin, begin, "line", end),
                lines(end, "line1"))

        # If multiple marker pairs exist, only the last one is considered
        self.assertBlockInFile(
                lines(begin, "block1", end, "out1", begin, "block2", end, "out2"),
                lines(begin, "block1", end, "out1", begin, "test", end, "out2"),
                block="test")

        self.assertBlockInFile(
                lines(begin, "block1", end, "out1", begin, "block2", end, "out2"),
                lines(begin, "block1", end, "out1", "out2"))

        # Replace with a noop
        self.assertBlockInFile(
                lines(begin, "block1", end, "out1", begin, "block2", end, "out2"),
                block="block2")

    def test_insert(self):
        self.maxDiff = None

        begin = "# BEGIN ANSIBLE MANAGED BLOCK"
        end = "# END ANSIBLE MANAGED BLOCK"

        def lines(*lns) -> List[str]:
            res = []
            for line in lns:
                res.append(line.strip() + "\n")
            return res

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines("line0", "line1", "line2", begin, "test", end),
                block="test")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines(begin, "test", end, "line0", "line1", "line2"),
                block="test", insertbefore="BOF")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines(begin, "test", end, "line0", "line1", "line2"),
                block="test", insertbefore="line0")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines("line0", begin, "test", end, "line1", "line2"),
                block="test", insertbefore="line1")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines("line0", "line1", begin, "test", end, "line2"),
                block="test", insertbefore="line2")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines("line0", begin, "test", end, "line1", "line2"),
                block="test", insertafter="line0")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines("line0", "line1", begin, "test", end, "line2"),
                block="test", insertafter="line1")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines("line0", "line1", "line2", begin, "test", end),
                block="test", insertafter="line2")

        self.assertBlockInFile(
                lines("line0", "line1", "line2"),
                lines("line0", "line1", "line2", begin, "test", end),
                block="test", insertafter="EOF")


class TestBlockInFileLocal(LocalTestMixin, unittest.TestCase):
    pass


class TestBlockInFileMitogen(LocalMitogenTestMixin, unittest.TestCase):
    pass
