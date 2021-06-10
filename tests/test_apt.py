from __future__ import annotations
import unittest
import os
from transilience.unittest import ActionTestMixin, ChrootTestMixin
from transilience import actions


class TestApt(ActionTestMixin, ChrootTestMixin, unittest.TestCase):
    def test_install_existing(self):
        self.run_action(
            actions.Apt(
                name=["dbus"],
                state="present",
            ), changed=False)

    def test_install_missing(self):
        self.assertFalse(self.system.context.call(os.path.exists, "/usr/bin/hello"))

        self.run_action(
            actions.Apt(
                name=["hello"],
                state="present",
            ))

        self.assertTrue(self.system.context.call(os.path.exists, "/usr/bin/hello"))
