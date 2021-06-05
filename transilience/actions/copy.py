from __future__ import annotations
from typing import TYPE_CHECKING, Union, Optional
from dataclasses import dataclass
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

    def write_content(self):
        if isinstance(self.content, str):
            self.content = self.content.encode()

        with self.write_file_atomically(self.dest, "wb") as fd:
            fd.write(self.content)

    def write_src(self, system: transilience.system.System):
        with self.write_file_atomically(self.dest, "wb") as fd:
            system.transfer_file(self.src, fd)

    def run(self, system: transilience.system.System):
        super().run(system)
        if self.content is not None:
            self.write_content()
        else:
            self.write_src(system)
