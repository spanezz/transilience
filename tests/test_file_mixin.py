from __future__ import annotations
from typing import Optional, Union
import contextlib
import unittest
from unittest import mock
from transilience.actions.common import FileMixin
from transilience.actions.action import Action
from transilience.unittest import FileModeMixin


class ComputedPermsAction(FileMixin, Action):
    pass


class TestComputeFsPerms(FileModeMixin, unittest.TestCase):
    @contextlib.contextmanager
    def umask(self, umask: Optional[int]):
        if umask is None:
            yield
        else:
            with mock.patch("os.umask", return_value=umask):
                yield

    def assertComputedPerms(
            self,
            mode: Union[None, int, str],
            orig: Optional[int],
            expected: int,
            is_dir: bool = False,
            umask: Optional[int] = None):
        with self.umask(umask):
            act = ComputedPermsAction(mode=mode)
            act.run(None)
            computed = act._compute_fs_perms(orig, is_dir=is_dir)
            self.assertFileModeEqual(computed, expected)

    def test_none(self):
        self.assertComputedPerms(mode=None, orig=None, expected=0o644, umask=0o022)
        self.assertComputedPerms(mode=None, orig=None, expected=0o755, umask=0o022, is_dir=True)
        self.assertComputedPerms(mode=None, orig=0o644, expected=None)

    def test_int(self):
        self.assertComputedPerms(mode=0o644, orig=None, expected=0o644)
        self.assertComputedPerms(mode=0o644, orig=0o644, expected=None)

    def test_str(self):
        self.assertComputedPerms(mode="u=rw,g=r,o=r", orig=None, expected=0o644)
        self.assertComputedPerms(mode="u=rw,g=r,o=r", orig=0o644, expected=None)

        self.assertComputedPerms(mode="u=rwX,g=rX,o=rX", orig=None, expected=0o644)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=rX", orig=0o644, expected=None)

        self.assertComputedPerms(mode="u=rwX,g=rX,o=rX", orig=None, is_dir=True, expected=0o755)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=rX", orig=0o644, is_dir=True, expected=0o755)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=rX", orig=0o744, is_dir=True, expected=0o755)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=rX", orig=0o755, is_dir=True, expected=None)

        self.assertComputedPerms(mode="ug=rwX,o=rX", orig=None, expected=0o664)
        self.assertComputedPerms(mode="ug=rwX,o=rX", orig=0o664, expected=None)

        self.assertComputedPerms(mode="ug=rwX,o=rX", orig=None, is_dir=True, expected=0o775)
        self.assertComputedPerms(mode="ug=rwX,o=rX", orig=0o664, is_dir=True, expected=0o775)
        self.assertComputedPerms(mode="ug=rwX,o=rX", orig=0o744, is_dir=True, expected=0o775)
        self.assertComputedPerms(mode="ug=rwX,o=rX", orig=0o775, is_dir=True, expected=None)

        self.assertComputedPerms(mode="u=rwX,g=rX,o=", orig=None, expected=0o640)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=", orig=0o640, expected=None)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=", orig=0o222, expected=0o640)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=", orig=None, is_dir=True, expected=0o750)
        self.assertComputedPerms(mode="u=rwX,g=rX,o=", orig=0o222, is_dir=True, expected=0o750)

        self.assertComputedPerms(mode="u=rwx,g=rxs,o=", orig=None, expected=0o2750)
        self.assertComputedPerms(mode="u=rwx,g=rxs,o=", orig=0o2750, expected=None)
        self.assertComputedPerms(mode="u=rwx,g=rxs,o=", orig=0o222, expected=0o2750)
        self.assertComputedPerms(mode="u=rwx,g=rxs,o=", orig=None, is_dir=True, expected=0o2750)
        self.assertComputedPerms(mode="u=rwx,g=rxs,o=", orig=0o222, is_dir=True, expected=0o2750)

    def test_equal_x(self):
        # Ported from coreutils's test suite
        self.assertComputedPerms(mode="a=r,=x", orig=0o644, umask=0o005, expected=0o110)
        self.assertComputedPerms(mode="a=r,=xX", orig=0o644, umask=0o005, expected=0o110)
        self.assertComputedPerms(mode="a=r,=Xx", orig=0o644, umask=0o005, expected=0o110)
        self.assertComputedPerms(mode="a=r,=x,=X", orig=0o644, umask=0o005, expected=0o110)
        self.assertComputedPerms(mode="a=r,=X,=x", orig=0o644, umask=0o005, expected=0o110)

    def test_equals(self):
        # Ported from coreutils's test suite
        expected = {
            "u": 0o700,
            "g": 0o070,
            "o": 0o007,
        }
        for src in "ugo":
            for dest in "ugo":
                if src == dest:
                    continue
                self.assertComputedPerms(mode=f"a=,{src}=rwx,{dest}={src},{src}=", orig=0o644, expected=expected[dest])
