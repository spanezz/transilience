from __future__ import annotations
from typing import TYPE_CHECKING, Optional, IO
from dataclasses import dataclass
import hashlib
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
    checksum: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        if self.dest is None:
            raise TypeError(f"{self.__class__}.dest cannot be None")

        # If we are given a source file, compute its checksum
        if self.src is not None:
            if self.content is not None:
                raise ValueError(f"{self.__class__}: src and content cannot both be set")

            with open(self.src, "rb") as fd:
                checksum = self._sha1sum(fd)

            if self.checksum is None:
                self.checksum = checksum
            elif self.checksum != checksum:
                raise RuntimeError(f"{self.src!r} has SHA1 {checksum!r} but 'checksum' value is {self.checksum!r}")
        elif self.content is not None:
            h = hashlib.sha1()
            if isinstance(self.content, str):
                h.update(self.content.encode())
            else:
                h.update(self.content)
            checksum = h.hexdigest()

            if self.checksum is None:
                self.checksum = checksum
            elif self.checksum != checksum:
                raise RuntimeError(f"{self.__class__}.content has SHA1 {checksum!r}"
                                   f"but 'checksum' value is {self.checksum!r}")
        else:
            raise ValueError(f"{self.__class__}: one of src and content needs to be set")

    def _sha1sum(self, fd: IO):
        h = hashlib.sha1()
        while True:
            buf = fd.read(40960)
            if not buf:
                break
            h.update(buf)
        return h.hexdigest()

    def _dest_shasum(self):
        try:
            with open(self.dest, "rb") as fd:
                return self._sha1sum(fd)
        except FileNotFoundError:
            return None

    def write_content(self):
        checksum = self._dest_shasum()

        # If file exists, checksum it, and if the hashes are the same, don't transfer
        if checksum is not None and checksum == self.checksum:
            self.set_path_permissions_if_exists(self.dest)
            return

        if isinstance(self.content, str):
            content = self.content.encode()
        else:
            content = self.content

        with self.write_file_atomically(self.dest, "wb") as fd:
            fd.write(content)

    def write_src(self, system: transilience.system.System):
        checksum = self._dest_shasum()

        # If file exists, checksum it, and if the hashes are the same, don't transfer
        if checksum is not None and checksum == self.checksum:
            self.set_path_permissions_if_exists(self.dest)
            return

        with self.write_file_atomically(self.dest, "w+b") as fd:
            system.transfer_file(self.src, fd)
            fd.seek(0)
            checksum = self._sha1sum(fd)
            if checksum != self.checksum:
                raise RuntimeError(f"{self.dest!r} has SHA1 {checksum!r} after receiving it,"
                                   f"but 'checksum' value is {self.checksum!r}")

    def run(self, system: transilience.system.System):
        super().run(system)
        if self.content is not None:
            self.write_content()
        else:
            self.write_src(system)
