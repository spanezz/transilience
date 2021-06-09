from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Union, List
from dataclasses import dataclass
import re
from .common import FileAction

if TYPE_CHECKING:
    import transilience.system


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/blockinfile_module.html
@dataclass
class BlockInFile(FileAction):
    """
    Same as ansible's builtin.blockinfile.

    Not yet implemented:
     - backup
     - unsafe_writes
     - validate
    """
    path: str = ""
    block: Union[str, bytes] = ""
    insertafter: Optional[str] = None
    insertbefore: Optional[str] = None
    marker: str = "# {mark} ANSIBLE MANAGED BLOCK"
    marker_begin: str = "BEGIN"
    marker_end: str = "END"
    create: bool = False
    state: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        if self.path == "":
            raise TypeError(f"{self.__class__}.path cannot be empty")

        if self.insertbefore is not None and self.insertafter is not None:
            raise ValueError(f"{self.__class__}: insertbefore and insertafter cannot both be set")

        if self.block == "":
            if self.state == "present":
                raise ValueError(f"{self.__class__}: then the block is empty, state bust be absent")
            elif self.state is None:
                self.state = "absent"
        else:
            if self.state is None:
                self.state = "present"

    def edit_lines(self, lines: List[bytes]):
        # Compute markers
        marker_begin = self.marker.format(mark=self.marker_begin).encode()
        marker_end = self.marker.format(mark=self.marker_end).encode()

        # Compute insert position
        if self.insertbefore is None:
            if self.insertafter in (None, "EOF"):
                pos = "EOF"
                insertre = None
            else:
                pos = "AFTER"
                insertre = re.compile(self.insertafter.encode(errors='surrogate_or_strict'))
        else:
            if self.insertbefore == "BOF":
                pos = "BOF"
                insertre = None
            else:
                pos = "BEFORE"
                insertre = re.compile(self.insertbefore.encode(errors='surrogate_or_strict'))

        # Block to insert/replace
        if self.block and self.state == "present":
            if isinstance(self.block, str):
                block = self.block.encode()
            else:
                block = self.block

            blocklines = [marker_begin + b"\n"]
            for line in block.splitlines():
                if not line.endswith(b"\n"):
                    line += b"\n"
                blocklines.append(line)
            blocklines.append(marker_end + b"\n")
        else:
            blocklines = []

        # Look for the last matching block in the file, and for the last line
        # matching insertre
        line_begin = None
        last_block = None
        insertre_pos = None
        for lineno, line in enumerate(lines):
            # print("SCAN", lineno, line, line_begin, last_block, insertre_pos)
            if line_begin is None:
                if line.rstrip() == marker_begin:
                    line_begin = lineno
            else:
                if line.rstrip() == marker_end:
                    last_block = (line_begin, lineno)
                    line_begin = None

            if insertre is not None and insertre.search(line):
                insertre_pos = lineno
        if line_begin is not None:
            last_block = (line_begin, lineno + 1)

        # Do the edit
        # print("EDIT", last_block, pos, insertre, blocklines, lines)
        if last_block is None:
            if pos == "EOF":
                lines += blocklines
            elif pos == "BOF":
                lines[0:0] = blocklines
            elif pos == "BEFORE":
                lines[insertre_pos:insertre_pos] = blocklines
            elif pos == "AFTER":
                lines[insertre_pos + 1:insertre_pos + 1] = blocklines
        else:
            lines[last_block[0]:last_block[1] + 1] = blocklines

    def run(self, system: transilience.system.System):
        super().run(system)
        path = self.get_path_object(self.path, follow=True)
        lines: List[bytes]
        if path is None:
            if not self.create:
                return
            dest = self.path
            lines = []
        else:
            dest = path.path
            # Read the original contents of the file
            with open(dest, "rb") as fd:
                lines = fd.readlines()

        orig_lines = list(lines)
        self.edit_lines(lines)

        # If file exists, and contents would not be changed, don't write it
        if orig_lines == lines:
            self.set_path_object_permissions(path)
            return

        # Write out the new contents
        with self.write_file_atomically(dest, "wb") as fd:
            for line in lines:
                fd.write(line)
