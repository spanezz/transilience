from __future__ import annotations
from typing import TYPE_CHECKING, Union, Optional
from dataclasses import dataclass
import contextlib
import tempfile
import stat
import pwd
import grp
import os

if TYPE_CHECKING:
    import transilience.system


@dataclass
class FileMixin:
    owner: Optional[str] = None
    group: Optional[str] = None
    mode: Union[str, int, None] = None

    # TODO: seuser
    # TODO: serole
    # TODO: selevel
    # TODO: setype
    # TODO: attributes
    # TODO: follow=dict(type='bool', default=False)

    def _compute_fs_perms(self, orig: Optional[int], is_dir=False) -> Optional[int]:
        if self.mode is None:
            # Mode not specified
            if orig is None:
                # For newly created file or dirs, use the current umask
                cur_umask = os.umask(0)
                os.umask(cur_umask)
                if is_dir:
                    return 0o777 & ~cur_umask
                else:
                    return 0o666 & ~cur_umask
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
            raise NotImplementedError("String modes not yet implemented")

    def _set_fd_perms(self, path: str, fd: int):
        mode = self._compute_fs_perms(orig=None, is_dir=False)
        if mode is not None:
            os.fchmod(fd, mode)
            self.mode = mode
            self.log.info("%s: file mode set to 0o%o", path, mode)

        if self.owner != -1 or self.group != -1:
            os.fchown(fd, self.owner, self.group)
            self.log.info("%s: file ownership set to %d %d", path, self.owner, self.group)

    def set_path_permissions_if_exists(self, path: str):
        """
        Set the permissions of an existing file.

        Calls self.set_changed() if the filesystem gets changed
        """
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return

        mode = self._compute_fs_perms(orig=stat.S_IMODE(st.st_mode), is_dir=False)
        if mode is not None:
            os.chmod(path, mode)
            self.mode = mode
            self.set_changed()
            self.log.info("%s: file mode set to 0o%o", path, self.mode)
        else:
            self.mode = stat.S_IMODE(st.st_mode)

        if (self.owner != -1 and self.owner != st.st_uid) or (self.group != -1 and self.group != st.st_gid):
            self.set_changed()
            os.chown(path, self.owner, self.group)
            self.log.info("%s: file ownership set to %d %d", path, self.owner, self.group)
        else:
            self.owner = st.st_uid
            self.group = st.st_gid

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

        # if use_umask:
        #     cur_umask = os.umask(0)
        #     os.umask(cur_umask)
        #     chmod &= ~cur_umask

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
        if self.owner is not None:
            self.owner = pwd.getpwnam(self.owner).pw_uid
        else:
            self.owner = -1
        if self.group is not None:
            self.group = grp.getgrnam(self.group).gr_gid
        else:
            self.group = -1

        # TODO: parse mode if it is a string
