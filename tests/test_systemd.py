from __future__ import annotations
from typing import Optional, List, Dict
import unittest
from unittest import mock
import inspect
import shlex
import uuid
from transilience.unittest import ActionTestMixin, LocalTestMixin, ChrootTestMixin
from transilience.actions import builtin


class TestSystemd(ActionTestMixin, LocalTestMixin, unittest.TestCase):
    def assertSystemd(
                self,
                file_state: Optional[str] = None,
                active_state: Optional[str] = None,
                called: Optional[List[str]] = None,
                changed=True,
                **kwargs):
        unit_info: Dict[str, str] = {}
        if file_state is not None:
            unit_info["UnitFileState"] = file_state
        if active_state is not None:
            unit_info["ActiveState"] = active_state
        if called is None:
            called = []
        actual_called = []

        def collect(args, **kw):
            self.assertIn("systemctl", args[0])
            actual_called.append(" ".join(shlex.quote(a) for a in args[1:]))

        with mock.patch("transilience.actions.systemd.Systemd.get_unit_info", return_value=unit_info):
            # Try check mode first
            with mock.patch("subprocess.run", collect):
                orig = builtin.systemd(check=True, **kwargs)
                self.run_action(orig, changed=changed)
                self.assertEqual(actual_called, [])

            with mock.patch("subprocess.run", collect):
                orig = builtin.systemd(**kwargs)
                return self.run_action(orig, changed=changed), actual_called

    def test_daemon_reload(self):
        act, called = self.assertSystemd(daemon_reload=True, changed=False)
        self.assertEqual(called, ["daemon-reload"])

    def test_daemon_reexec(self):
        act, called = self.assertSystemd(daemon_reexec=True, changed=False)
        self.assertEqual(called, ["daemon-reexec"])

    def test_enable(self):
        act, called = self.assertSystemd(
                unit="test", file_state="disabled", active_state="inactive", enabled=False, changed=False)
        self.assertEqual(called, [])

        act, called = self.assertSystemd(
                unit="test", file_state="disabled", active_state="inactive", enabled=True, changed=True)
        self.assertEqual(called, ["enable test"])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="inactive", enabled=True, changed=False)
        self.assertEqual(called, [])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="inactive", enabled=False, changed=True)
        self.assertEqual(called, ["disable test"])

    def test_mask(self):
        act, called = self.assertSystemd(
                unit="test", file_state="disabled", active_state="inactive", masked=False, changed=False)
        self.assertEqual(called, [])

        act, called = self.assertSystemd(
                unit="test", file_state="disabled", active_state="inactive", masked=True, changed=True)
        self.assertEqual(called, ["mask test"])

        act, called = self.assertSystemd(
                unit="test", file_state="masked", active_state="inactive", masked=True, changed=False)
        self.assertEqual(called, [])

        act, called = self.assertSystemd(
                unit="test", file_state="masked", active_state="inactive", masked=False, changed=True)
        self.assertEqual(called, ["unmask test"])

    def test_start(self):
        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="inactive", state="stopped", changed=False)
        self.assertEqual(called, [])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="inactive", state="started", changed=True)
        self.assertEqual(called, ["start test"])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="active", state="started", changed=False)
        self.assertEqual(called, [])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="active", state="stopped", changed=True)
        self.assertEqual(called, ["stop test"])

    def test_reload(self):
        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="active", state="restarted", changed=True)
        self.assertEqual(called, ["restart test"])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="inactive", state="restarted", changed=True)
        self.assertEqual(called, ["start test"])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="active", state="reloaded", changed=True)
        self.assertEqual(called, ["reload test"])

        act, called = self.assertSystemd(
                unit="test", file_state="enabled", active_state="inactive", state="reloaded", changed=True)
        self.assertEqual(called, ["start test"])


class TestSystemdReal(ActionTestMixin, ChrootTestMixin, unittest.TestCase):
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
