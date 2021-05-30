from __future__ import annotations
from typing import Union, Optional
from dataclasses import dataclass
import pwd
import grp
import os
from .action import Action


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/copy_module.html
@dataclass
class Copy(Action):
    """
    Same as ansible's builtin.copy.

    Not yet implemented:
     - attributes
     - backup
     - checksum
     - decrypt
     - directory_mode
     - follow
     - force
     - local_follow
     - remote_src
     - selevel
     - serole
     - setype
     - seuser
     - src
     - unsafe_writes
     - validate
    """
    dest: str
    src: Optional[str] = None
    content: Optional[bytes] = None
    owner: Optional[str] = None
    group: Optional[str] = None
    mode: Union[str, int, None] = None

    def __post_init__(self):
        super().__post_init__()
        # TODO: this needs to be executed locally
        if self.src is None and self.content is None:
            raise ValueError(f"{self.__class__}: one of src or content must be set")
        if self.src is not None:
            if os.path.isdir(self.src):
                # TODO: set contents to compressed tarball
                raise NotImplementedError(f"{self.__class__}: copying directories not yet implemented")
            else:
                with open(self.src, "rb") as fd:
                    self.content = fd.read()

    def set_mode(self, fd: int):
        if self.owner != -1 or self.group != -1:
            os.fchown(fd, self.owner, self.group)
            self.log.info("%s: file ownership set to %d %d", self.dest, self.owner, self.group)

        if self.mode is not None:
            if isinstance(self.mode, str):
                raise NotImplementedError("string modes not yet implemented")
            os.fchmod(fd, self.mode)
            self.log.info("%s: file mode set to 0o%o", self.dest, self.mode)

    def run(self):
        # Resolve/validate owner and group before we perform any action
        if self.owner is not None:
            self.owner = pwd.getpwnam(self.owner).pw_uid
        else:
            self.owner = -1
        if self.group is not None:
            self.group = grp.getgenam(self.group).gr_gid
        else:
            self.group = -1

        # TODO: atomic write
        with open(self.dest, "wb") as fd:
            fd.write(self.content)

            self.set_mode(fd.fileno())
