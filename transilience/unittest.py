from __future__ import annotations
import contextlib
import atexit
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


class LocalTestMixin:
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
