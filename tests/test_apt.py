from __future__ import annotations
import unittest
import os
from transilience.unittest import ChrootTestMixin
from transilience import actions


class TestApt(ChrootTestMixin, unittest.TestCase):
    def test_install_existing(self):
        res = list(self.system.run_actions([
            actions.Apt(
                name="Install dbus",
                pkg=["dbus"],
                state="present",
            )
        ]))

        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], actions.Apt)

    def test_install_missing(self):
        self.assertFalse(self.system.context.call(os.path.exists, "/usr/games/cowsay"))

        res = list(self.system.run_actions([
            actions.Apt(
                name="Install cowsay",
                pkg=["cowsay"],
                state="present",
            )
        ]))

        self.assertTrue(self.system.context.call(os.path.exists, "/usr/games/cowsay"))

        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], actions.Apt)
