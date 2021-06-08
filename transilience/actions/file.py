from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
import shutil
import os
from .action import Action
from .common import FileMixin

if TYPE_CHECKING:
    import transilience.system


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/file_module.html
@dataclass
class File(FileMixin, Action):
    """
    Same as ansible's builtin.file.

    Not yet implemented:
     - state=hard
     - state=link
     - access_time
     - modification_time
     - follow
     - force
     - modification_time_format
     - src
     - unsafe_writes
    """
    path: str = None
    state: str = "file"
    recurse: bool = False
    # follow: bool = True
    # src: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        if self.path is None:
            raise TypeError(f"{self.__class__}.path cannot be None")
        if self.recurse is True and self.state != "directory":
            raise ValueError(f"{self.__class__}.recurse only makes sense when state=directory")

    def do_absent(self):
        if os.path.isdir(self.path):
            shutil.rmtree(self.path)
            self.log.info("%s: removed directory recursively")
            self.set_changed()
        elif os.path.exists(self.path):
            os.unlink(self.path)
            self.log.info("%s: removed")
            self.set_changed()

    def do_file(self):
        self.set_path_permissions_if_exists(self.path)

    def do_touch(self):
        with self.create_file_if_missing(self.path) as fd:
            pass

        if fd is None:
            # The file already exists
            self.set_path_permissions_if_exists(self.path)

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
            if self.recurse:
                # TODO: use dirfd
                for root, dirs, files in os.walk(self.path):
                    for fn in dirs + files:
                        self.set_path_permissions_if_exists(os.path.join(root, fn), record=False)

            self.set_path_permissions_if_exists(self.path)
        else:
            self._mkpath(self.path)
            self.set_changed()

    def run(self, system: transilience.system.System):
        super().run(system)

        meth = getattr(self, f"do_{self.state}", None)
        if meth is None:
            raise NotImplementedError(f"File state {self.state!r} is not implemented")
        return meth()
