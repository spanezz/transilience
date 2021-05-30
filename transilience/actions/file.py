from __future__ import annotations
from typing import Union, Optional
from dataclasses import dataclass
import shutil
import pwd
import grp
import os
from .action import Action


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/file_module.html
@dataclass
class File(Action):
    """
    Same as ansible's builtin.file.

    Not yet implemented:
     - state=hard
     - state=link
     - access_time
     - modification_time
     - attributes
     - follow
     - force
     - mode as string (integer works)
     - modification_time_format
     - recurse
     - selevel
     - serole
     - setype
     - seuser
     - src
     - unsafe_writes
    """
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
        needs_set_mode = self.pw_owner is not None or self.pw_group is not None or self.mode is not None

        try:
            if needs_set_mode:
                mode = 0
            else:
                mode = 0o666
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode=mode)
            self.log.info("%s: file created", self.path)
        except FileExistsError:
            if needs_set_mode:
                fd = os.open(self.path, os.O_RDONLY)
            else:
                fd = None

        if fd is not None:
            try:
                self.set_mode(fd)
            finally:
                os.close(fd)

    def _mkpath(self, path: str):
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            self._mkpath(parent)

        if self.mode is not None:
            mode = self.mode
        else:
            mode = 0o777

        self.log.info("%s: creating directory, mode: 0x%o", path, mode)
        os.mkdir(path, mode=mode)

        if self.pw_owner or self.pw_group:
            uid = self.pw_owner.pw_uid if self.pw_owner is not None else -1
            gid = self.pw_group.gr_gid if self.pw_group is not None else -1
            self.log.info("%s: setting ownership to %d:%d", path, uid, gid)
            os.chown(path, uid, gid)

    def do_directory(self):
        if os.path.isdir(self.path):
            if self.mode:
                self.log.info("%s: setting mode to 0o%o", self.path, self.mode)
                os.chmod(self.path, self.mode)
            if self.pw_owner or self.pw_group:
                uid = self.pw_owner.pw_uid if self.pw_owner is not None else -1
                gid = self.pw_group.gr_gid if self.pw_group is not None else -1
                self.log.info("%s: setting ownership to %d:%d", self.path, uid, gid)
                os.chown(self.path, uid, gid)
        else:
            self._mkpath(self.path)

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
