from __future__ import annotations
import unittest
import inspect
import uuid
from transilience.unittest import ActionTestMixin, ChrootTestMixin
from transilience.actions import builtin


class TestSystemd(ActionTestMixin, ChrootTestMixin, unittest.TestCase):
    def assertSystemd(self, changed=True, **kwargs):
        orig = builtin.systemd(**kwargs)
        return self.run_action(orig, changed=changed)

    def setUp(self):
        self.unit_name = str(uuid.uuid4())

        self.run_action(builtin.copy(
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

        self.run_action(builtin.systemd(daemon_reload=True), changed=False)

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
