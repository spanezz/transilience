from __future__ import annotations
from typing import TYPE_CHECKING, Union, Optional
from dataclasses import dataclass
import os
from .action import Action
from .common import FileMixin

if TYPE_CHECKING:
    import transilience.system


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/copy_module.html
@dataclass
class Copy(FileMixin, Action):
    """
    Same as ansible's builtin.copy.

    Not yet implemented:
     - backup
     - checksum
     - decrypt
     - directory_mode
     - follow
     - force
     - local_follow
     - remote_src
     - src
     - unsafe_writes
     - validate
     - src as directory
    """
    dest: str = None
    src: Optional[str] = None
    content: Optional[str, bytes] = None
    owner: Optional[str] = None
    group: Optional[str] = None
    mode: Union[str, int, None] = None

    def __post_init__(self):
        super().__post_init__()
        if self.dest is None:
            raise TypeError(f"{self.__class__}.dest cannot be None")

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
        self.log.info("%s: file mode set to 0o%o", self.dest, self.mode)

    def write_content(self):
        if isinstance(self.content, str):
            self.content = self.content.encode()

        with self.write_file_atomically(self.dest, "wb") as fd:
            fd.write(self.content)

    def write_src(self, system: transilience.system.System):
        with system.transfer_file(self.src, self.dest, chmod=None) as fd:
            self.set_mode(fd.fileno())

    def run(self, system: transilience.system.System):
        super().run(system)
        if self.content is not None:
            self.write_content()
        else:
            self.write_src(system)
