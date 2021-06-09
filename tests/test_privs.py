from __future__ import annotations
import unittest
import os
from transilience.unittest import privs


class TestPrivs(unittest.TestCase):
    def assertUnprivileged(self):
        uid, euid, suid = os.getresuid()
        self.assertEqual(uid, privs.user_uid)
        self.assertEqual(euid, privs.user_uid)
        self.assertEqual(suid, 0)

        gid, egid, sgid = os.getresgid()
        self.assertEqual(gid, privs.user_gid)
        self.assertEqual(egid, privs.user_gid)
        self.assertEqual(sgid, 0)

    def assertPrivileged(self):
        uid, euid, suid = os.getresuid()
        self.assertEqual(uid, 0)
        self.assertEqual(euid, 0)
        self.assertEqual(suid, privs.user_uid)

        gid, egid, sgid = os.getresgid()
        self.assertEqual(gid, 0)
        self.assertEqual(egid, 0)
        self.assertEqual(sgid, privs.user_gid)

    def test_default(self):
        self.assertTrue(privs.dropped)
        self.assertUnprivileged()

    def test_root(self):
        self.assertTrue(privs.dropped)
        self.assertUnprivileged()
        with privs.root():
            self.assertFalse(privs.dropped)
            self.assertPrivileged()
        self.assertTrue(privs.dropped)
        self.assertUnprivileged()
