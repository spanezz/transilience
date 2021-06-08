from __future__ import annotations
from typing import Optional
import contextlib
import subprocess
import logging
import atexit
import shlex
import uuid
import os

log = logging.getLogger(__name__)


class ProcessPrivs:
    def __init__(self):
        self.orig_uid, self.orig_euid, self.orig_suid = os.getresuid()
        self.orig_gid, self.orig_egid, self.orig_sgid = os.getresgid()

        if "SUDO_UID" not in os.environ:
            raise RuntimeError("Tests need to be run under sudo")

        self.user_uid = int(os.environ["SUDO_UID"])
        self.user_gid = int(os.environ["SUDO_GID"])

        self.dropped = False

    def drop(self):
        if self.dropped:
            return
        os.setresgid(self.user_gid, self.user_gid, 0)
        os.setresuid(self.user_uid, self.user_uid, 0)
        self.dropped = True

    def regain(self):
        if not self.dropped:
            return
        os.setresuid(self.orig_suid, self.orig_suid, self.user_uid)
        os.setresgid(self.orig_sgid, self.orig_sgid, self.user_gid)
        self.dropped = False

    @contextlib.contextmanager
    def root(self):
        if not self.dropped:
            yield
        else:
            self.regain()
            try:
                yield
            finally:
                self.drop()

    @contextlib.contextmanager
    def user(self):
        if self.dropped:
            yield
        else:
            self.drop()
            try:
                yield
            finally:
                self.regain()


privs = ProcessPrivs()
privs.drop()


class Chroot:
    running_chroots = {}

    def __init__(self, name: str, chroot_dir: Optional[str] = None):
        self.name = name
        if chroot_dir is None:
            self.chroot_dir = self.get_chroot_dir(name)
        else:
            self.chroot_dir = chroot_dir
        self.machine_name = f"transilience-{uuid.uuid4()}"

    def start(self):
        """
        Start nspawn on this given chroot.

        The systemd-nspawn command is run contained into its own unit using
        systemd-run
        """
        unit_config = [
            'KillMode=mixed',
            'Type=notify',
            'RestartForceExitStatus=133',
            'SuccessExitStatus=133',
            'Slice=machine.slice',
            'Delegate=yes',
            'TasksMax=16384',
            'WatchdogSec=3min',
        ]

        cmd = ["systemd-run"]
        for c in unit_config:
            cmd.append(f"--property={c}")

        cmd.extend((
            "systemd-nspawn",
            "--quiet",
            "--ephemeral",
            f"--directory={self.chroot_dir}",
            f"--machine={self.machine_name}",
            "--boot",
            "--notify-ready=yes"))

        log.info("%s: starting machine using image %s", self.machine_name, self.chroot_dir)

        log.debug("%s: running %s", self.machine_name, " ".join(shlex.quote(c) for c in cmd))
        with privs.root():
            subprocess.run(cmd, check=True, capture_output=True)
        log.debug("%s: started", self.machine_name)
        self.running_chroots[self.machine_name] = self

    def stop(self):
        cmd = ["machinectl", "terminate", self.machine_name]
        log.debug("%s: running %s", self.machine_name, " ".join(shlex.quote(c) for c in cmd))
        with privs.root():
            subprocess.run(cmd, check=True, capture_output=True)
        log.debug("%s: stopped", self.machine_name)
        del self.running_chroots[self.machine_name]

    @classmethod
    def create(cls, chroot_name: str) -> "Chroot":
        res = cls(chroot_name)
        res.start()
        return res

    @classmethod
    def get_chroot_dir(cls, chroot_name: str):
        chroot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_chroots", chroot_name))
        if not os.path.isdir(chroot_dir):
            raise RuntimeError(f"{chroot_dir} does not exists or is not a chroot directory")
        return chroot_dir


# We need to use atextit, because unittest won't run
# tearDown/tearDownClass/tearDownModule methods in case of KeyboardInterrupt
# and we need to make sure to terminate the nspawn containers at exit
@atexit.register
def cleanup():
    # Use a list to prevent changing running_chroots during iteration
    for chroot in list(Chroot.running_chroots.values()):
        chroot.stop()


class ActionTestMixin:
    """
    Test case mixin with common shortcuts for running actions
    """
    def run_action(self, action, changed=True):
        res = list(self.system.run_actions([action]))
        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], action.__class__)
        self.assertEqual(res[0].result.changed, changed)
        self.assertEqual(res[0].uuid, action.uuid)
        return res[0]


class LocalTestMixin:
    """
    Mixin to run tests over a 'local' connection to the same system where tests
    are run
    """
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from transilience.system import Local
        cls.system = Local()


class LocalMitogenTestMixin:
    """
    Mixin to run tests over a 'local' connection to the same system where tests
    are run
    """
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import mitogen
        from transilience.system import Mitogen
        cls.broker = mitogen.master.Broker()
        cls.router = mitogen.master.Router(cls.broker)
        cls.system = Mitogen("workdir", "local", router=cls.router)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.broker.shutdown()


class ChrootTestMixin:
    """
    Mixin to run tests over a setns connection to an ephemeral systemd-nspawn
    container running one of the test chroots
    """
    chroot_name = "buster"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import mitogen
        from transilience.system import Mitogen
        cls.broker = mitogen.master.Broker()
        cls.router = mitogen.master.Router(cls.broker)
        cls.chroot = Chroot.create(cls.chroot_name)
        with privs.root():
            cls.system = Mitogen(
                    cls.chroot.name, "setns", kind="machinectl",
                    python_path="/usr/bin/python3",
                    container=cls.chroot.machine_name, router=cls.router)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.broker.shutdown()
        cls.chroot.stop()
