from __future__ import annotations
import unittest
import inspect
import uuid
from transilience.unittest import ChrootTestMixin
from transilience import actions


class TestSystemd(ChrootTestMixin, unittest.TestCase):
    def run_action(self, action):
        res = list(self.system.run_actions([action]))
        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], action.__class__)
        return res[0]

    def assertSystemd(self, changed=True, **kwargs):
        orig = actions.Systemd(name="test action", **kwargs)
        act = self.run_action(orig)
        self.assertEqual(act.changed, changed)
        self.assertEqual(orig.uuid, act.uuid)
        return act

    def setUp(self):
        self.unit_name = str(uuid.uuid4())

        act = self.run_action(actions.Copy(
                name="setup unit",
                dest=f"/usr/lib/systemd/system/{self.unit_name}.service",
                content=inspect.cleandoc(f"""
                [Unit]
                Description=Test Unit {self.unit_name}
                [Service]
                Type=simple
                ExecStart=/usr/bin/sleep 6h
                ExecReload=/bin/true
                [Install]
                WantedBy=multi-user.target
                """)
            )
        )
        self.assertTrue(act.changed)

        self.run_action(actions.Systemd(name="daemon_reload", daemon_reload=True))

    def test_daemon_reload(self):
        self.assertSystemd(daemon_reload=True, changed=False)

    def test_daemon_reexec(self):
        self.assertSystemd(daemon_reexec=True, changed=False)

    def test_enable(self):
        self.assertSystemd(unit=self.unit_name, enabled=False, changed=False)
        self.assertSystemd(unit=self.unit_name, enabled=True, changed=True)
        self.assertSystemd(unit=self.unit_name, enabled=True, changed=False)
        self.assertSystemd(unit=self.unit_name, enabled=False, changed=True)
        self.assertSystemd(unit=self.unit_name, enabled=False, changed=False)

    def test_mask(self):
        self.assertSystemd(unit=self.unit_name, masked=False, changed=False)
        self.assertSystemd(unit=self.unit_name, masked=True, changed=True)
        self.assertSystemd(unit=self.unit_name, masked=True, changed=False)
        self.assertSystemd(unit=self.unit_name, masked=False, changed=True)
        self.assertSystemd(unit=self.unit_name, masked=False, changed=False)

    def test_start(self):
        self.assertSystemd(unit=self.unit_name, state="stopped", changed=False)
        self.assertSystemd(unit=self.unit_name, state="started", changed=True)
        self.assertSystemd(unit=self.unit_name, state="started", changed=False)
        self.assertSystemd(unit=self.unit_name, state="stopped", changed=True)

    def test_reload(self):
        self.assertSystemd(unit=self.unit_name, state="started", changed=True)
        self.assertSystemd(unit=self.unit_name, state="restarted", changed=True)
        self.assertSystemd(unit=self.unit_name, state="restarted", changed=True)
        self.assertSystemd(unit=self.unit_name, state="reloaded", changed=True)
        self.assertSystemd(unit=self.unit_name, state="reloaded", changed=True)
