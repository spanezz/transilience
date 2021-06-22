from __future__ import annotations
from typing import Optional, Union, Dict
import contextlib
import subprocess
import logging
import atexit
import shlex
import stat
import uuid
import os
from .actions import ResultState

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
    running_chroots: Dict[str, "Chroot"] = {}

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


class FileState:
    def __init__(self, path: str):
        self.path = path

    def __str__(self):
        return repr(self)

    def __eq__(self, other: "FileState"):
        return self.__class__ == other.__class__

    @classmethod
    def scan(self, path: str) -> "FileState":
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return FileStateMissing(path)

        if stat.S_ISLNK(st.st_mode):
            return FileStateLink(path, st)
        elif stat.S_ISDIR(st.st_mode):
            return FileStateDir(path, st)
        else:
            return FileStateFile(path, st)


class FileStateMissing(FileState):
    def __repr__(self):
        return f"{self.path!r}: missing"


class FileStateStat(FileState):
    def __init__(self, path: str, st: os.stat_result):
        super().__init__(path)
        self.stat = st

    def __eq__(self, other: "FileStateStat"):
        if not super().__eq__(other):
            return False

        return self.stat == other.stat


class FileStateLink(FileStateStat):
    def __init__(self, path: str, st: os.stat_result):
        super().__init__(path, st)
        self.contents = os.readlink(path)

    def __repr__(self):
        return (f"{self.path!r}: symlink to {self.contents!r},"
                f" mode=0o{stat.S_IMODE(self.stat.st_mode):o},"
                f" uid={stat.st_uid}, gid={stat.st_gid}")

    def __eq__(self, other: "FileStateLink"):
        if not super().__eq__(other):
            return False
        return self.contents == other.contents


class FileStateFile(FileStateStat):
    def __init__(self, path: str, st: os.stat_result):
        super().__init__(path, st)
        with open(path, "rb") as fd:
            self.contents = fd.read()

    def __repr__(self):
        return (f"{self.path!r}: file,"
                f" mode=0o{stat.S_IMODE(self.stat.st_mode):o},"
                f" uid={self.stat.st_uid}, gid={self.stat.st_gid}"
                f" contents={self.contents!r}")

    def __eq__(self, other: "FileStateFile"):
        if not super().__eq__(other):
            return False
        return self.contents == other.contents


class FileStateDir(FileStateStat):
    def __init__(self, path: str, st: os.stat_result):
        super().__init__(path, st)
        self.contents = {}
        for fn in os.listdir(path):
            p = os.path.join(path, fn)
            self.contents[fn] = FileState.scan(p)

    def __repr__(self):
        return (f"{self.path!r}: dir"
                f" mode=0o{stat.S_IMODE(self.stat.st_mode):o},"
                f" uid={stat.st_uid}, gid={stat.st_gid}")

    def __eq__(self, other: "FileStateFile"):
        if not super().__eq__(other):
            return False
        return self.contents == other.contents


class FileModeMixin:
    """
    Functions useful when working with file modes
    """
    @contextlib.contextmanager
    def assertUnchanged(self, path: str):
        orig = FileState.scan(path)

        try:
            yield
        finally:
            new = FileState.scan(path)

            self.assertEqual(new, orig)

    def assertFileModeEqual(self, actual: Union[None, int, os.stat_result], expected: Optional[int]):
        if isinstance(actual, os.stat_result):
            actual = stat.S_IMODE(actual.st_mode)
        if actual == expected:
            return
        if actual is None:
            fmta = "None"
        else:
            fmta = f"0o{actual:o}"
        if expected is None:
            fmte = "None"
        else:
            fmte = f"0o{expected:o}"
        self.fail(f"permissions {fmta} is not the expected {fmte}")


class ActionTestMixin:
    """
    Test case mixin with common shortcuts for running actions
    """
    def run_action(self, action, changed=True):
        act = self.system.execute(action)
        self.assertIsInstance(act, action.__class__)
        if changed:
            self.assertEqual(act.result.state, ResultState.CHANGED)
        else:
            self.assertEqual(act.result.state, ResultState.NOOP)
        self.assertEqual(act.uuid, action.uuid)
        return act


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

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.system.close()

    def setUp(self):
        super().setUp()
        self.system.caches = {}


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
        cls.system.close()
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
        cls.system.close()
        cls.broker.shutdown()
        cls.chroot.stop()
