from __future__ import annotations
import unittest
from transilience.unittest import ActionTestMixin, ChrootTestMixin
from transilience.actions import builtin


user_sequence = 0


class TestUser(ActionTestMixin, ChrootTestMixin, unittest.TestCase):
    def setUp(self):
        global user_sequence
        self.user_name = f"user{user_sequence}"
        user_sequence += 1

    def assertUser(self, changed=True, **kwargs):
        kwargs.setdefault("name", self.user_name)

        # Quick and dirty way of testing check mode: if it performs actions,
        # the next call to the action should report not changed.
        #
        # There can be more serious tests after a refactoring of the User
        # action implementations
        orig = builtin.user(check=True, **kwargs)
        self.run_action(orig, changed=changed)

        orig = builtin.user(**kwargs)
        return self.run_action(orig, changed=changed)

    def test_create(self):
        act = self.assertUser(state="present")
        self.assertIsNotNone(act.uid)
        self.assertIsNotNone(act.group)
        self.assertIsNotNone(act.comment)
        self.assertIsNotNone(act.home)
        self.assertIsNotNone(act.shell)

        act = self.assertUser(state="present", changed=False)

    def test_remove(self):
        self.assertUser(state="present")
        self.assertUser(state="absent")
        self.assertUser(state="absent", changed=False)
