from __future__ import annotations
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

    def __init__(self, chroot_dir: str):
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
            subprocess.run(cmd, check=True)
        log.debug("%s: started", self.machine_name)
        self.running_chroots[self.machine_name] = self

    def stop(self):
        cmd = ["machinectl", "terminate", self.machine_name]
        log.debug("%s: running %s", self.machine_name, " ".join(shlex.quote(c) for c in cmd))
        with privs.root():
            subprocess.run(cmd, check=True)
        log.debug("%s: stopped", self.machine_name)
        del self.running_chroots[self.machine_name]

    @classmethod
    def create(cls, chroot_name: str) -> "Chroot":
        res = cls(cls.get_chroot_dir(chroot_name))
        res.start()
        return res

    @classmethod
    def get_chroot_dir(cls, chroot_name: str):
        chroot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_chroots", chroot_name))
        if not os.path.isdir(chroot_dir):
            raise RuntimeError(f"{chroot_dir} does not exists or is not a chroot directory")
        return chroot_dir


@atexit.register
def cleanup():
    # Use a list to prevent changing running_chroots during iteration
    for chroot in list(Chroot.running_chroots.values()):
        chroot.stop()


class LocalTestMixin:
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
