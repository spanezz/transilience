from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Union, List, Dict, Any, cast
from dataclasses import dataclass, field
import subprocess
import glob
import os
import shlex
from .action import Action
from . import builtin

if TYPE_CHECKING:
    import transilience.system


@builtin.action(name="command")
@dataclass
class Command(Action):
    """
    Same as Ansible's
    [builtin.command](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/command_module.html).

    Not yet implemented:

     * strip_empty_ends
    """
    argv: List[str] = field(default_factory=list)
    chdir: Optional[str] = None
    cmd: Optional[str] = None
    creates: Optional[str] = None
    removes: Optional[str] = None
    stdin: Union[str, bytes, None] = None
    stdin_add_newline: bool = True

    # stdout and stderr filled on execution
    stdout: Optional[bytes] = None
    stderr: Optional[bytes] = None

    def __post_init__(self):
        super().__post_init__()
        if not self.argv and not self.cmd:
            raise TypeError(f"{self.__class__}: one of args and cmd needs to be set")

    def summary(self):
        if self.cmd:
            return f"Run {self.cmd!r}"
        else:
            return "Run " + " ".join(shlex.quote(x) for x in self.argv)

    def run(self, system: transilience.system.System):
        super().run(system)

        if self.creates:
            if self.chdir:
                creates = os.path.join(self.chdir, self.creates)
            else:
                creates = self.creates
            if glob.glob(creates):
                return

        if self.removes:
            if self.chdir:
                removes = os.path.join(self.chdir, self.removes)
            else:
                removes = self.removes
            if not glob.glob(removes):
                return

        kwargs: Dict[str, Any] = {
            "capture_output": True,
            "check": True,
        }
        if self.chdir:
            kwargs["cwd"] = self.chdir

        if self.stdin is not None:
            if isinstance(self.stdin, bytes):
                stdin = self.stdin
            else:
                if self.stdin_add_newline:
                    stdin = (self.stdin + "\n").encode()
                else:
                    stdin = self.stdin.encode()
            kwargs["input"] = stdin

        if self.argv:
            args = self.argv
        else:
            # We can cast, because __post_init__ makes sure self.cmd is not
            # None if self.argv is None
            args = shlex.split(cast(str, self.cmd))

        self.set_changed()
        res = subprocess.run(args, **kwargs)
        self.stdout = res.stdout
        self.stderr = res.stderr
