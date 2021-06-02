from __future__ import annotations
import unittest
import os
from transilience.unittest import ChrootTestMixin
from transilience import actions


class TestFile(ChrootTestMixin, unittest.TestCase):
    def test_install_existing(self):
        self.system.run_actions([
            actions.Apt(
                name="Install dbus",
                pkg=["dbus"],
                state="present",
            )
        ])

    def test_install_missing(self):
        self.assertFalse(self.system.remote.call(os.path.exists, "/usr/games/cowsay"))

        self.system.run_actions([
            actions.Apt(
                name="Install cowsay",
                pkg=["cowsay"],
                state="present",
            )
        ])

        self.assertTrue(self.system.remote.call(os.path.exists, "/usr/games/cowsay"))
