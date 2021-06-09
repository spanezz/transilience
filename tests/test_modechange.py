from __future__ import annotations
import unittest
import stat
from transilience.utils import modechange


class TestModeChange(unittest.TestCase):
    def test_compile_group(self):
        mc = modechange.ModeChange.compile_group("=644")
        self.assertEqual(mc.op, "=")
        self.assertEqual(mc.flag, modechange.MODE_ORDINARY_CHANGE)
        self.assertEqual(mc.affected, modechange.CHMOD_MODE_BITS)
        self.assertEqual(mc.value, 0o644)
        self.assertEqual(mc.mentioned, modechange.CHMOD_MODE_BITS)

        mc = modechange.ModeChange.compile_group("u=rw")
        self.assertEqual(mc.op, "=")
        self.assertEqual(mc.flag, modechange.MODE_ORDINARY_CHANGE)
        self.assertEqual(mc.affected, stat.S_ISUID | stat.S_IRWXU)
        self.assertEqual(mc.value,
                         stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH |
                         stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        self.assertEqual(mc.mentioned, stat.S_ISUID | stat.S_IRWXU)

        mc = modechange.ModeChange.compile_group("u=rX")
        self.assertEqual(mc.op, "=")
        self.assertEqual(mc.flag, modechange.MODE_X_IF_ANY_X)
        self.assertEqual(mc.affected, stat.S_ISUID | stat.S_IRWXU)
        self.assertEqual(mc.value,
                         stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self.assertEqual(mc.mentioned, stat.S_ISUID | stat.S_IRWXU)
        self.assertEqual(modechange.ModeChange.adjust(0o640, False, 000, [mc]), (0o440, mc.affected))

        mc = modechange.ModeChange.compile_group("g=r")
        self.assertEqual(mc.op, "=")
        self.assertEqual(mc.flag, modechange.MODE_ORDINARY_CHANGE)
        self.assertEqual(mc.affected, stat.S_ISGID | stat.S_IRWXG)
        self.assertEqual(mc.value, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self.assertEqual(mc.mentioned, stat.S_ISGID | stat.S_IRWXG)

        mc = modechange.ModeChange.compile_group("g+r")
        self.assertEqual(mc.op, "+")
        self.assertEqual(mc.flag, modechange.MODE_ORDINARY_CHANGE)
        self.assertEqual(mc.affected, stat.S_ISGID | stat.S_IRWXG)
        self.assertEqual(mc.value, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self.assertEqual(mc.mentioned, stat.S_ISGID | stat.S_IRWXG)

        mc = modechange.ModeChange.compile_group("g+w")
        self.assertEqual(mc.op, "+")
        self.assertEqual(mc.flag, modechange.MODE_ORDINARY_CHANGE)
        self.assertEqual(mc.affected, stat.S_ISGID | stat.S_IRWXG)
        self.assertEqual(mc.value, stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        self.assertEqual(mc.mentioned, stat.S_ISGID | stat.S_IRWXG)
        self.assertEqual(modechange.ModeChange.adjust(0o440, False, 000, [mc]), (0o460, 0o020))

        mc = modechange.ModeChange.compile_group("o=r")
        self.assertEqual(mc.op, "=")
        self.assertEqual(mc.flag, modechange.MODE_ORDINARY_CHANGE)
        self.assertEqual(mc.affected, stat.S_ISVTX | stat.S_IRWXO)
        self.assertEqual(mc.value, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self.assertEqual(mc.mentioned, stat.S_ISVTX | stat.S_IRWXO)

        mc = modechange.ModeChange.compile_group("o=")
        self.assertEqual(mc.op, "=")
        self.assertEqual(mc.flag, modechange.MODE_ORDINARY_CHANGE)
        self.assertEqual(mc.affected, stat.S_ISVTX | stat.S_IRWXO)
        self.assertEqual(mc.value, 0)
        self.assertEqual(mc.mentioned, stat.S_ISVTX | stat.S_IRWXO)
