from __future__ import annotations
from typing import TYPE_CHECKING, Union, Optional, BinaryIO, cast
from dataclasses import dataclass
import contextlib
import tempfile
import hashlib
import stat
import pwd
import grp
import os
from transilience.utils.modechange import ModeChange
from .action import Action

if TYPE_CHECKING:
    import transilience.system


class PathObject:
    """
    Information about what is pointed by an existing path in the filesystem
    """
    # It would be nice to support dir_fd, but we need to not follow symlinks
    # when doing chown/chmod, and at least chmod does not support using dir_fd
    # and follow_symlinks together.
    def __init__(self, path: str, follow: bool = True):
        self.path = path
        self.st = os.lstat(self.path)
        if stat.S_ISLNK(self.st.st_mode) and follow:
            self.st = os.stat(self.path)
            self.path = os.readlink(self.path)

    def __str__(self):
        return self.path

    def chmod(self, mode: int):
        if self.islink():
            try:
                os.chmod(self.path, mode, follow_symlinks=False)
            except NotImplementedError:
                pass
        else:
            os.chmod(self.path, mode)

    def chown(self, uid: int = -1, gid: int = -1):
        os.chown(self.path, uid, gid, follow_symlinks=False)

    def isdir(self) -> bool:
        return stat.S_ISDIR(self.st.st_mode)

    def islink(self) -> bool:
        return stat.S_ISLNK(self.st.st_mode)

    def walk(self, **kw):
        yield from os.walk(self.path)

    def sha1sum(self):
        with open(self.path, "rb") as fd:
            return self.compute_file_sha1sum(fd)

    @classmethod
    def compute_file_sha1sum(self, fd: BinaryIO) -> str:
        h = hashlib.sha1()
        while True:
            buf = fd.read(40960)
            if not buf:
                break
            h.update(buf)
        return h.hexdigest()


@dataclass
class FileAction(Action):
    owner: Union[str, int, None] = None
    group: Union[str, int, None] = None
    mode: Union[str, int, None] = None

    # TODO: seuser
    # TODO: serole
    # TODO: selevel
    # TODO: setype
    # TODO: attributes
    # TODO: follow=dict(type='bool', default=False)

    def __post_init__(self):
        super().__post_init__()
        # precompiled mode
        self._mode = None
        self._cur_umask = None

    def _compute_fs_perms(self, orig: Optional[int], is_dir: bool = False) -> Optional[int]:
        """
        Compute permissions that the referred file should have in the file system.

        * orig: original permissions, or None if the file has just been created
        * is_dir: True if working with a directory, False if working with a file
        """
        if self.mode is None:
            # Mode not specified
            if orig is None:
                # For newly created file or dirs, use the current umask
                if is_dir:
                    return 0o777 & ~self._cur_umask
                else:
                    return 0o666 & ~self._cur_umask
            else:
                # For existing file or dirs, do nothing
                return None
        elif isinstance(self.mode, int):
            if orig is None:
                # New files or dirs get self.mode
                return self.mode
            elif orig != self.mode:
                # Existing files get self.mode only if it changes their mode
                return self.mode
            else:
                return None
        else:
            if orig is None:
                new_mode, affected_bits = ModeChange.adjust(
                    oldmode=0,
                    is_dir=is_dir,
                    umask_value=self._cur_umask,
                    changes=self._mode)

                return new_mode
            else:
                new_mode, affected_bits = ModeChange.adjust(
                    oldmode=orig,
                    is_dir=is_dir,
                    umask_value=self._cur_umask,
                    changes=self._mode)

                if orig == new_mode:
                    return None
                else:
                    return new_mode

    def _set_fd_perms(self, path: str, fd: int):
        mode = self._compute_fs_perms(orig=None, is_dir=False)
        if mode is not None:
            os.fchmod(fd, mode)
            self.mode = mode
            self.log.info("%s: file mode set to 0o%o", path, mode)

        if self.owner != -1 or self.group != -1:
            os.fchown(fd, cast(int, self.owner), cast(int, self.group))
            self.log.info("%s: file ownership set to %d %d", path, self.owner, self.group)

    def get_path_object(
            self,
            path: str,
            follow: Optional[bool] = None) -> Optional[PathObject]:
        """
        Return a PathObject from a given path
        """
        if follow is None:
            follow = getattr(self, "follow", True)
        try:
            return PathObject(path=path, follow=follow)
        except FileNotFoundError:
            return None

    def set_path_object_permissions(self, path: Optional[PathObject], record=True):
        """
        Set the permissions of an existing file.

        Calls self.set_changed() if the filesystem gets changed
        """
        if path is None:
            return
        mode = self._compute_fs_perms(orig=stat.S_IMODE(path.st.st_mode), is_dir=path.isdir())
        if mode is not None:
            path.chmod(mode)
            if record:
                self.mode = mode
            self.set_changed()
            self.log.info("%s: file mode set to 0o%o", path, mode)
        else:
            if record:
                self.mode = stat.S_IMODE(path.st.st_mode)

        if (self.owner != -1 and self.owner != path.st.st_uid) or (self.group != -1 and self.group != path.st.st_gid):
            self.set_changed()
            path.chown(cast(int, self.owner), cast(int, self.group))
            self.log.info("%s: file ownership set to %d %d", path, self.owner, self.group)
        else:
            if record:
                self.owner = path.st.st_uid
                self.group = path.st.st_gid

    @contextlib.contextmanager
    def create_file_if_missing(self, path: str, mode="w+b", **kwargs):
        """
        Create the given file, only if it does not yet exist in the file system

        Calls self.set_changed() if the filesystem gets changed
        """
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, mode=0o600)
            self.log.info("%s: file created", path)
        except FileExistsError:
            yield None
            return

        # If we are here, it means we created the file. If anything fails here,
        # we need to remove it on exit
        try:
            with open(fd, mode, closefd=True, **kwargs) as outfd:
                yield outfd
                self._set_fd_perms(path, fd)

            self.set_changed()
        except Exception:
            os.unlink(path)
            raise

    @contextlib.contextmanager
    def write_file_atomically(self, path: str, mode="w+b", **kwargs):
        """
        Atomically rewrite the given file.

        The path to the file is created with the default filesystem owners and
        permissions, if missing.

        Leave the file with the permissions as described by the class members.

        Extra kwargs are passed to Python's open() function.

        Calls self.set_changed() if the filesystem gets changed
        """
        dirname = os.path.dirname(path)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

        fd, tmppath = tempfile.mkstemp(dir=dirname, text="b" not in mode, prefix=path)
        outfd = open(fd, mode, closefd=True, **kwargs)
        try:
            yield outfd
            outfd.flush()
            # if sync:
            #     os.fdatasync(fd)
            self.log.info("%s: file contents written", path)

            self._set_fd_perms(path, fd)

            os.rename(tmppath, path)
            self.log.info("%s: original file replaced", path)
            self.set_changed()
        except Exception:
            os.unlink(tmppath)
            raise
        finally:
            outfd.close()

    def run(self, system: transilience.system.System):
        super().run(system)

        # Resolve/validate owner and group before we perform any action
        # From this point on we can cast self.owner and self.group to int
        if self.owner is not None:
            if isinstance(self.owner, str):
                self.owner = pwd.getpwnam(self.owner).pw_uid
        else:
            self.owner = -1
        if self.group is not None:
            if isinstance(self.group, str):
                self.group = grp.getgrnam(self.group).gr_gid
        else:
            self.group = -1

        if isinstance(self.mode, str):
            self._mode = ModeChange.compile(self.mode)

        self._cur_umask = os.umask(0)
        os.umask(self._cur_umask)
