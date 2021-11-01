from __future__ import annotations
import contextlib
import os
import shlex
import tempfile
import time
import unittest
from unittest import mock
from typing import Dict, Tuple

from transilience.unittest import ActionTestMixin, LocalTestMixin, ChrootTestMixin
from transilience.actions import builtin
from transilience.actions.apt import DpkgStatus


class MockDpkgStatus(DpkgStatus):
    def __init__(self):
        self.path: str = "/dev/null"
        self.arch: str = "amd64"
        self.mtime: float = None
        self.packages: Dict[Tuple[str, str], Tuple[str, str]] = {}

    def update(self):
        pass


class MockLogFile:
    def __init__(self, path: str):
        self.path = path

    def lines(self):
        to_remove = frozenset((
            "-q", "-y",
            "--option=Dpkg::Options::=--force-confdef",
            "--option=Dpkg::Options::=--force-confold"))
        res = []
        try:
            with open(self.path, "rt") as fd:
                for line in fd:
                    args = [a for a in shlex.split(line.rstrip()) if a not in to_remove]
                    res.append(" ".join(shlex.quote(a) for a in args))
        except FileNotFoundError:
            pass
        return res


class TestApt(ActionTestMixin, LocalTestMixin, unittest.TestCase):
    @contextlib.contextmanager
    def mock_apt(self, upgraded=0, new=0, removed=0, held=0, returncode=0):
        with tempfile.TemporaryDirectory() as workdir:
            apt_get = os.path.join(workdir, "apt-get")
            logfile = os.path.join(workdir, "apt-get.log")
            with open(apt_get, "wt") as fd:
                print(f"""#!/bin/sh
echo "$@" >> {logfile}
echo 'Moo!'
echo '{upgraded} upgraded, {new} newly installed, {removed} to remove and {held} not upgraded.'
exit {returncode}
""", file=fd)
            os.chmod(apt_get, 0o755)

            with mock.patch("transilience.actions.apt.Apt.find_apt_get", return_value=apt_get):
                yield MockLogFile(logfile)

    def run_apt(self, changed=True, upgraded=0, new=0, removed=0, held=0, **kwargs):
        with self.mock_apt(upgraded, new, removed, held) as log:
            self.run_action(builtin.apt(**kwargs), changed=changed)
            return log.lines()

    def test_update(self):
        lines = self.run_apt(changed=True, update_cache=True)
        self.assertEqual(lines, ["update"])

        with mock.patch("transilience.actions.apt.Apt.get_cache_mtime", return_value=time.time() - 1000):
            lines = self.run_apt(changed=True, update_cache=True, cache_valid_time=100)
            self.assertEqual(lines, ["update"])

            lines = self.run_apt(changed=False, update_cache=True, cache_valid_time=3000)
            self.assertEqual(lines, [])

    def test_check_update(self):
        lines = self.run_apt(changed=True, update_cache=True, check=True)
        self.assertEqual(lines, ["--simulate update"])

        with mock.patch("transilience.actions.apt.Apt.get_cache_mtime", return_value=time.time() - 1000):
            lines = self.run_apt(changed=True, update_cache=True, cache_valid_time=100, check=True)
            self.assertEqual(lines, ["--simulate update"])

            lines = self.run_apt(changed=False, update_cache=True, cache_valid_time=3000, check=True)
            self.assertEqual(lines, [])

    def test_upgrade(self):
        lines = self.run_apt(changed=False, upgrade="yes", upgraded=0)
        self.assertEqual(lines, ["upgrade --with-new-pkgs"])

        lines = self.run_apt(upgrade="yes", upgraded=1)
        self.assertEqual(lines, ["upgrade --with-new-pkgs"])

        lines = self.run_apt(upgrade="safe", upgraded=1)
        self.assertEqual(lines, ["upgrade --with-new-pkgs"])

        lines = self.run_apt(upgrade="dist", upgraded=1)
        self.assertEqual(lines, ["dist-upgrade"])

        lines = self.run_apt(upgrade="full", upgraded=1)
        self.assertEqual(lines, ["dist-upgrade"])

        lines = self.run_apt(changed=False, name=["*"], state="latest", upgraded=0)
        self.assertEqual(lines, ["upgrade --with-new-pkgs"])

        lines = self.run_apt(name=["*"], state="latest", upgraded=1)
        self.assertEqual(lines, ["upgrade --with-new-pkgs"])

    def test_check_upgrade(self):
        lines = self.run_apt(changed=False, upgrade="yes", upgraded=0, check=True)
        self.assertEqual(lines, ["--simulate upgrade --with-new-pkgs"])

        lines = self.run_apt(upgrade="yes", upgraded=1, check=True)
        self.assertEqual(lines, ["--simulate upgrade --with-new-pkgs"])

        lines = self.run_apt(upgrade="safe", upgraded=1, check=True)
        self.assertEqual(lines, ["--simulate upgrade --with-new-pkgs"])

        lines = self.run_apt(upgrade="dist", upgraded=1, check=True)
        self.assertEqual(lines, ["--simulate dist-upgrade"])

        lines = self.run_apt(upgrade="full", upgraded=1, check=True)
        self.assertEqual(lines, ["--simulate dist-upgrade"])

        lines = self.run_apt(changed=False, name=["*"], state="latest", upgraded=0, check=True)
        self.assertEqual(lines, ["--simulate upgrade --with-new-pkgs"])

        lines = self.run_apt(name=["*"], state="latest", upgraded=1, check=True)
        self.assertEqual(lines, ["--simulate upgrade --with-new-pkgs"])

    def test_install(self):
        with mock.patch("transilience.actions.apt.Apt.mark_manually_installed", return_value=None):
            status = MockDpkgStatus()
            with mock.patch("transilience.actions.apt.DpkgStatus", lambda: status):
                lines = self.run_apt(name=["python3"], state="present", new=1)
                self.assertEqual(lines, ["install python3"])

                lines = self.run_apt(changed=False, name=["python3"], state="present", new=0)
                self.assertEqual(lines, ["install python3"])

                status.packages = {("python3", "amd64"): ("3.7.3-1", "install ok installed")}
                lines = self.run_apt(changed=False, name=["python3"], state="present", new=0)
                self.assertEqual(lines, [])

                status.packages = {("python3", "amd64"): ("3.7.3-1", "deinstall ok config-files")}
                lines = self.run_apt(name=["python3"], state="present", new=1)
                self.assertEqual(lines, ["install python3"])

                status.packages = {("python3", "arm64"): ("3.7.3-1", "install ok installed")}
                lines = self.run_apt(name=["python3"], state="present", new=1)
                self.assertEqual(lines, ["install python3"])

                lines = self.run_apt(changed=False, name=["python3:arm64"], state="present", new=1)
                self.assertEqual(lines, [])

    def test_check_install(self):
        with mock.patch("transilience.actions.apt.Apt.mark_manually_installed", return_value=None):
            status = MockDpkgStatus()
            with mock.patch("transilience.actions.apt.DpkgStatus", lambda: status):
                lines = self.run_apt(name=["python3"], state="present", new=1, check=True)
                self.assertEqual(lines, ["--simulate install python3"])

                lines = self.run_apt(changed=False, name=["python3"], state="present", new=0, check=True)
                self.assertEqual(lines, ["--simulate install python3"])

                status.packages = {("python3", "amd64"): ("3.7.3-1", "install ok installed")}
                lines = self.run_apt(changed=False, name=["python3"], state="present", new=0, check=True)
                self.assertEqual(lines, [])

                status.packages = {("python3", "amd64"): ("3.7.3-1", "deinstall ok config-files")}
                lines = self.run_apt(name=["python3"], state="present", new=1, check=True)
                self.assertEqual(lines, ["--simulate install python3"])

                status.packages = {("python3", "arm64"): ("3.7.3-1", "install ok installed")}
                lines = self.run_apt(name=["python3"], state="present", new=1, check=True)
                self.assertEqual(lines, ["--simulate install python3"])

                lines = self.run_apt(changed=False, name=["python3:arm64"], state="present", new=1, check=True)
                self.assertEqual(lines, [])

    def test_remove(self):
        status = MockDpkgStatus()
        with mock.patch("transilience.actions.apt.DpkgStatus", lambda: status):
            lines = self.run_apt(changed=False, name=["python3"], state="absent", removed=1)
            self.assertEqual(lines, [])

            status.packages = {("python3", "amd64"): ("3.7.3-1", "install ok installed")}
            lines = self.run_apt(name=["python3"], state="absent", removed=1)
            self.assertEqual(lines, ["remove python3"])
            lines = self.run_apt(name=["python3"], state="absent", purge=True, removed=1)
            self.assertEqual(lines, ["--purge remove python3"])

            status.packages = {("python3", "amd64"): ("3.7.3-1", "deinstall ok config-files")}
            lines = self.run_apt(changed=False, name=["python3"], state="absent", removed=1)
            self.assertEqual(lines, [])
            lines = self.run_apt(name=["python3"], state="absent", purge=True, removed=1)
            self.assertEqual(lines, ["--purge remove python3"])

            status.packages = {("python3", "arm64"): ("3.7.3-1", "install ok installed")}
            lines = self.run_apt(changed=False, name=["python3"], state="absent", removed=1)
            self.assertEqual(lines, [])
            lines = self.run_apt(name=["python3:arm64"], state="absent", purge=True, removed=1)
            self.assertEqual(lines, ["--purge remove python3:arm64"])

    def test_check_remove(self):
        status = MockDpkgStatus()
        with mock.patch("transilience.actions.apt.DpkgStatus", lambda: status):
            lines = self.run_apt(changed=False, name=["python3"], state="absent", removed=1, check=True)
            self.assertEqual(lines, [])

            status.packages = {("python3", "amd64"): ("3.7.3-1", "install ok installed")}
            lines = self.run_apt(name=["python3"], state="absent", removed=1, check=True)
            self.assertEqual(lines, ["--simulate remove python3"])
            lines = self.run_apt(name=["python3"], state="absent", purge=True, removed=1, check=True)
            self.assertEqual(lines, ["--simulate --purge remove python3"])

            status.packages = {("python3", "amd64"): ("3.7.3-1", "deinstall ok config-files")}
            lines = self.run_apt(changed=False, name=["python3"], state="absent", removed=1, check=True)
            self.assertEqual(lines, [])
            lines = self.run_apt(name=["python3"], state="absent", purge=True, removed=1, check=True)
            self.assertEqual(lines, ["--simulate --purge remove python3"])

            status.packages = {("python3", "arm64"): ("3.7.3-1", "install ok installed")}
            lines = self.run_apt(changed=False, name=["python3"], state="absent", removed=1, check=True)
            self.assertEqual(lines, [])
            lines = self.run_apt(name=["python3:arm64"], state="absent", purge=True, removed=1, check=True)
            self.assertEqual(lines, ["--simulate --purge remove python3:arm64"])


class TestAptReal(ActionTestMixin, ChrootTestMixin, unittest.TestCase):
    def test_install_existing(self):
        self.run_action(
            builtin.apt(
                name=["dbus"],
                state="present",
            ), changed=False)

    def test_install_missing(self):
        self.assertFalse(self.system.context.call(os.path.exists, "/usr/bin/hello"))

        self.run_action(
            builtin.apt(
                name=["hello"],
                state="present",
            ))

        self.assertTrue(self.system.context.call(os.path.exists, "/usr/bin/hello"))

    def test_install_nonexisting(self):
        act = self.run_action(
            builtin.apt(
                name=["does-not-exist"],
                state="present",
            ), failed=True)
        self.assertEqual(act.result.exc_type, "CalledProcessError")
        self.assertEqual(act.result.exc_val,
                         "Command '['/usr/bin/apt-get', '-q', '-y', '--option=Dpkg::Options::=--force-confdef',"
                         " '--option=Dpkg::Options::=--force-confold', 'install', 'does-not-exist']'"
                         " returned non-zero exit status 100.")
        self.assertEqual(len(act.result.command_log), 1)
        cl = act.result.command_log[0]
        self.assertEqual(cl.cmdline, [
            '/usr/bin/apt-get', '-q', '-y',
            '--option=Dpkg::Options::=--force-confdef',
            '--option=Dpkg::Options::=--force-confold', 'install',
            'does-not-exist'])
        self.assertEqual(cl.stderr, "E: Unable to locate package does-not-exist\n")
