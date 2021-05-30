from __future__ import annotations
from typing import Union, Optional
from dataclasses import dataclass
import logging
import shutil
import pwd
import grp
import os
# from .system import System


# https://docs.ansible.com/ansible/latest/collections/index_module.html

@dataclass
class Action:
    name: str

    def __post_init__(self):
        self.log = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    def run(self):
        raise NotImplementedError(f"run not implemented for action {self.__class__.__name__}: {self.name}")


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/file_module.html#ansible-collections-ansible-builtin-file-module  # noqa
@dataclass
class File(Action):
    path: str
    owner: Optional[str] = None
    group: Optional[str] = None
    mode: Union[str, int, None] = None
    state: str = "file"
    # follow: bool = True
    # src: Optional[str] = None

    def set_mode(self, fd: int):
        if self.pw_owner or self.pw_group:
            uid = self.pw_owner.pw_uid if self.pw_owner is not None else -1
            gid = self.pw_group.gr_gid if self.pw_group is not None else -1
            os.fchown(fd, uid, gid)
            self.log.info("%s: file ownership set to %d %d", self.path, uid, gid)

        if self.mode is not None:
            if isinstance(self.mode, str):
                raise NotImplementedError("string modes not yet implemented")
            os.fchmod(fd, self.mode)
            self.log.info("%s: file mode set to 0o%o", self.path, self.mode)

    def do_absent(self):
        if os.path.isdir(self.path):
            shutil.rmtree(self.path)
            self.log.info("%s: removed directory recursively")
        elif os.path.exists(self.path):
            os.unlink(self.path)
            self.log.info("%s: removed")

    def do_file(self):
        try:
            fd = os.open(self.path, os.O_RDONLY)
        except FileNotFoundError:
            return

        try:
            self.set_mode(fd)
        finally:
            os.close(fd)

    def do_touch(self):
        needs_chmod = self.pw_owner is not None or self.pw_group is not None or self.mode is not None

        try:
            if needs_chmod:
                mode = 0
            else:
                mode = 0o666
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode=mode)
            self.log.info("%s: file created", self.path)
        except FileExistsError:
            if needs_chmod:
                fd = os.open(self.path, os.O_RDONLY)
            else:
                fd = None

        if fd is not None:
            try:
                self.set_mode(fd)
            finally:
                os.close(fd)

    def run(self):
        # Resolve/validate owner and group before we perform any action
        if self.owner is not None:
            self.pw_owner = pwd.getpwnam(self.owner)
        else:
            self.pw_owner = None
        if self.group is not None:
            self.pw_group = grp.getgenam(self.group)
        else:
            self.pw_group = None

        meth = getattr(self, f"do_{self.state}", None)
        if meth is None:
            raise NotImplementedError(f"File state {self.state!r} is not implemented")
        return meth()


# @dataclass
# class AptInstall(Action):
#     packages: Sequence[str]
#     recommends: bool = False
#
#     def run(self, system: System):
#         """
#         Install the given package(s), if they are not installed yet
#         """
#         cmd = ["apt", "-y", "install"]
#         if not self.recommends:
#             cmd.append("--no-install-recommends")
#
#         has_packages = False
#         for pkg in self.packages:
#             if system.has_file("var", "lib", "dpkg", "info", f"{pkg}.list"):
#                 continue
#             cmd.append(pkg)
#             has_packages = True
#
#         if not has_packages:
#             return
#
#         system.run(cmd)
#
#
# @dataclass
# class AptRemove(Action):
#     packages: Sequence[str]
#     purge: bool = False
#
#     def run(self, system: System):
#         """
#         Remove the given packages
#         """
#         cmd = ["apt", "-y", "remove" if self.purge is False else "purge"]
#         for pkg in self.packages:
#             # TODO: check in /var/lib/dpkg if they are already removed/purged
#             cmd.append(pkg)
#         system.run(cmd)
#
#
# @dataclass
# class AptInstallDeb(Action):
#     packages: Sequence[str]
#     recommends: bool = False
#
#     def run(self, system: System):
#         """
#         Install the given package(s), if they are not installed yet
#         """
#         with system.tempdir() as workdir:
#             system_paths = []
#             for package in self.packages:
#                 system.copy_to(package, workdir)
#                 system_paths.append(os.path.join(workdir, os.path.basename(package)))
#
#             cmd = ["apt", "-y", "install"]
#             if not self.recommends:
#                 cmd.append("--no-install-recommends")
#
#             for path in system_paths:
#                 cmd.append(path)
#
#             system.run(cmd)
