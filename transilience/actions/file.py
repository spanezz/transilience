from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass
import tempfile
import shutil
import os
from .common import FileAction, PathObject
from . import builtin

if TYPE_CHECKING:
    import transilience.system


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/file_module.html
@builtin.action(name="file")
@dataclass
class File(FileAction):
    """
    Same as ansible's builtin.file.

    Not yet implemented:
     - access_time
     - modification_time
     - modification_time_format
     - unsafe_writes
    """
    path: Optional[str] = None
    state: str = "file"
    recurse: bool = False
    src: Optional[str] = None
    follow: bool = True
    force: bool = False

    def __post_init__(self):
        super().__post_init__()
        if self.path is None:
            raise TypeError(f"{self.__class__}.path cannot be None")
        if self.recurse is True and self.state != "directory":
            raise ValueError(f"{self.__class__}.recurse only makes sense when state=directory")
        if self.state in ("link", "hard") and self.src is None:
            raise ValueError(f"{self.__class__} needs src when state {self.state}")

    def summary(self):
        if self.state == "file":
            return f"Set permissions/attributes of file {self.path!r}"
        elif self.state == "directory":
            return f"Setup directory {self.path!r}"
        elif self.state == "link":
            return f"Setup symlink {self.path!r}"
        elif self.state == "hard":
            return f"Setup hard link {self.path!r}"
        elif self.state == "touch":
            return f"Create file {self.path!r}"
        elif self.state == "absent":
            return f"Remove path {self.path!r}"
        else:
            return f"{self.__class__}: unknown state {self.state!r}"

    def do_file(self):
        path = self.get_path_object(self.path)
        if path is None:
            raise RuntimeError("f{path} does not exist")
        if path.isdir():
            raise RuntimeError("f{path} is a directory")
        if path.islink():
            raise RuntimeError("f{path} is a symlink")
        self.set_path_object_permissions(path)

    def _set_tree_perms(self, path: PathObject):
        for root, dirs, files in path.walk():
            for fn in dirs:
                self.set_path_object_permissions(
                        PathObject(os.path.join(root, fn), follow=False), record=False)
            for fn in files:
                self.set_path_object_permissions(
                        PathObject(os.path.join(root, fn), follow=False), record=False)

    def _mkpath(self, path: str):
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            self._mkpath(parent)

        self.log.info("%s: creating directory", path)
        os.mkdir(path)

        patho = self.get_path_object(path)
        self.set_path_object_permissions(patho, record=False)

    def do_directory(self):
        path = self.get_path_object(self.path)
        if path is None:
            # TODO: review
            self._mkpath(self.path)
            self.set_changed()
        elif path.isdir():
            if self.recurse:
                self._set_tree_perms(path)
            self.set_path_object_permissions(path)
        else:
            raise RuntimeError("f{path} exists and is not a directory")

    def do_link(self):
        path = self.get_path_object(self.path, follow=False)

        if path is not None:
            # Don't replace a non-link unless force is True
            if not path.islink() and not self.force:
                raise RuntimeError(f"{path} already exists, is not a link, and force is False")

            if path.isdir():
                target = os.path.join(path.path, self.src)
            else:
                target = os.path.join(os.path.dirname(path.path), self.src)
        else:
            target = os.path.join(os.path.dirname(self.path), self.src)

        target_po = self.get_path_object(target, follow=False)
        if target_po is None and not self.force:
            raise RuntimeError(f"{target!r} does not exists, and force is False")

        if path is None:
            os.symlink(target, self.path)
        elif path.islink():
            orig = os.readlink(self.path)
            if orig == target:
                return
            os.symlink(target, self.path)
        elif path.isdir():
            # tempfile.mktemp is deprecated, but I cannot find a better way to
            # atomically create a symlink with a nonconflicting name.
            tmp = tempfile.mktemp(prefix=self.path)
            os.symlink(target, tmp)
            try:
                os.rmdir(path.path)
                os.rename(tmp, self.path)
            except Exception:
                os.unlink(tmp)
                raise
        else:
            # tempfile.mktemp is deprecated, but I cannot find a better way to
            # atomically create a symlink with a nonconflicting name
            tmp = tempfile.mktemp(prefix=self.path)
            os.symlink(target, tmp)
            try:
                os.rename(tmp, self.path)
            except Exception:
                os.unlink(tmp)
                raise

        self.set_changed()
        path = self.get_path_object(self.path, follow=False)
        self.set_path_object_permissions(path)

    def do_hard(self):
        path = self.get_path_object(self.path, follow=False)

        target_po = self.get_path_object(self.src, follow=False)
        if target_po is None:
            raise RuntimeError(f"{self.src!r} does not exist")

        if path is None:
            os.link(self.src, self.path)
        elif path.islink():
            # tempfile.mktemp is deprecated, but I cannot find a better way to
            # atomically create a symlink with a nonconflicting name.
            tmp = tempfile.mktemp(prefix=self.path)
            os.link(self.src, tmp)
            try:
                os.unlink(self.path)
                os.rename(tmp, self.path)
            except Exception:
                os.unlink(tmp)
                raise
        elif path.isdir():
            # tempfile.mktemp is deprecated, but I cannot find a better way to
            # atomically create a symlink with a nonconflicting name.
            tmp = tempfile.mktemp(prefix=self.path)
            os.link(self.src, tmp)
            try:
                os.rmdir(path.path)
                os.rename(tmp, self.path)
            except Exception:
                os.unlink(tmp)
                raise
        else:
            target = self.get_path_object(self.src, follow=False)
            # noop if it's a link to the same target
            if (target.st.st_dev, target.st.st_ino) == (path.st.st_dev, path.st.st_ino):
                return
            # tempfile.mktemp is deprecated, but I cannot find a better way to
            # atomically create a symlink with a nonconflicting name
            tmp = tempfile.mktemp(prefix=self.path)
            os.link(self.src, tmp)
            try:
                os.rename(tmp, self.path)
            except Exception:
                os.unlink(tmp)
                raise

        self.set_changed()
        path = self.get_path_object(self.path, follow=False)
        self.set_path_object_permissions(path)

    def do_touch(self):
        with self.create_file_if_missing(self.path) as fd:
            pass

        if fd is None:
            # The file already exists
            path = self.get_path_object(self.path)
            self.set_path_object_permissions(path)

    def do_absent(self):
        path = self.get_path_object(self.path)
        if path is None:
            return

        if path.isdir():
            self.set_changed()
            shutil.rmtree(self.path, ignore_errors=False)
            self.log.info("%s: removed directory recursively")
        else:
            os.unlink(self.path)
            self.set_changed()
            self.log.info("%s: removed")

    def run(self, system: transilience.system.System):
        super().run(system)

        meth = getattr(self, f"do_{self.state}", None)
        if meth is None:
            raise NotImplementedError(f"File state {self.state!r} is not implemented")
        return meth()
