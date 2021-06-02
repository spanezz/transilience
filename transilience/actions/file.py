from __future__ import annotations
from typing import TYPE_CHECKING, Union, Optional
from dataclasses import dataclass
import shutil
import pwd
import grp
import os
from .action import Action

if TYPE_CHECKING:
    import transilience.system


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
        if self.owner != -1 or self.group != -1:
            os.fchown(fd, self.owner, self.group)
            self.log.info("%s: file ownership set to %d %d", self.dest, self.owner, self.group)

        if self.mode is not None:
            if isinstance(self.mode, str):
                raise NotImplementedError("string modes not yet implemented")
        else:
            cur_umask = os.umask(0)
            os.umask(cur_umask)
            self.mode = 0o666 & ~cur_umask

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
        needs_set_mode = self.owner != -1 or self.group != -1 or self.mode is not None

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

        if self.owner != -1 or self.group != -1:
            self.log.info("%s: directory ownership set to %d %d", path, self.owner, self.group)
            os.chown(path, self.owner, self.group)

    def do_directory(self):
        if os.path.isdir(self.path):
            if self.mode is None:
                cur_umask = os.umask(0)
                os.umask(cur_umask)
                self.mode = 0o777 & ~cur_umask

            self.log.info("%s: setting mode to 0o%o", self.path, self.mode)
            os.chmod(self.path, self.mode)

            if self.owner != -1 or self.group != -1:
                self.log.info("%s: directory ownership set to %d %d", self.path, self.owner, self.group)
                os.chown(self.path, self.owner, self.group)
        else:
            self._mkpath(self.path)

    def run(self, system: transilience.system.System):
        # Resolve/validate owner and group before we perform any action
        if self.owner is not None:
            self.owner = pwd.getpwnam(self.owner).pw_uid
        else:
            self.owner = -1
        if self.group is not None:
            self.group = grp.getgenam(self.group).gr_gid
        else:
            self.group = -1

        meth = getattr(self, f"do_{self.state}", None)
        if meth is None:
            raise NotImplementedError(f"File state {self.state!r} is not implemented")
        return meth()
