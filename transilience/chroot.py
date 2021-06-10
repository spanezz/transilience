from __future__ import annotations
from typing import List, Union, Optional, Iterator, Sequence
from contextlib import contextmanager
import subprocess
import tempfile
import logging
import shutil
import shlex
import os
from .system import System
from .utils import atomic_writer
from .actions import Action

log = logging.getLogger(__name__)


class Chroot(System):
    """
    Access a system inside a chroot
    """
    # Deprecated: this class is kept for compatibility with old code using
    # transilience that hasn't been ported to using actions
    def __init__(self, root: str):
        self.root = root

    def abspath(self, relpath: str, *args, create=False) -> str:
        """
        Get the out-of-chroot absolute path of ``relpath``.

        :arg create: if True, the destination is assumed to be a path, that is
                     created if it does not exist yet
        """
        if args:
            relpath = os.path.join(relpath, *args)
        res = os.path.join(self.root, relpath.lstrip("/"))
        if create:
            os.makedirs(res, exist_ok=True)
        return res

    def has_file(self, relpath: str, *args) -> bool:
        """
        Check if the given file exists in the chroot
        """
        return os.path.exists(self.abspath(relpath, *args))

    def getmtime(self, relpath: str) -> float:
        """
        Get the mtime of a file inside the chroot, or 0 if it does not exist
        """
        try:
            return os.path.getmtime(self.abspath(relpath))
        except FileNotFoundError:
            return 0

    def write_file(self, relpath: str, contents: str):
        """
        Atomically write/replace the file with the given content
        """
        dest = self.abspath(relpath)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.lexists(dest):
            os.unlink(dest)
        with atomic_writer(dest, "wt") as fd:
            fd.write(contents)

    def write_symlink(self, relpath: str, target: str):
        """
        Write/replace the file with a symlink to the given target
        """
        dest = self.abspath(relpath)
        os.makedirs(os.path.basename(dest), exist_ok=True)
        if os.path.lexists(dest):
            os.unlink(dest)
        os.symlink(target, dest)

    @contextmanager
    def tempdir(self) -> Iterator[str]:
        """
        Create a temporary working directory inside the chroot.

        Returns the relative path of the working directory from the root of the
        chroot.
        """
        with tempfile.TemporaryDirectory(dir=self.abspath("root")) as path:
            yield os.path.join("/", os.path.relpath(path, self.root))

    @contextmanager
    def edit_text_file(self, fname: str):
        """
        Edit a file by manipulating an array with its lines.

        Lines are automatically rstripped.

        If the list gets changed, it is written back.
        """
        dest = self.abspath(fname)
        with open(dest, "rt") as fd:
            lines = [line.rstrip() for line in fd]

        orig_lines = list(lines)
        yield lines

        if orig_lines != lines:
            with open(dest, "wt") as fd:
                for line in lines:
                    print(line, file=fd)

    def file_contents_replace(self, relpath: str, search: str, replace: str) -> bool:
        """
        Replace ``search`` with ``replace`` in ``relpath``.

        :return: True if the replace happened, False if ``relpath`` is
                 unchanged, or did not exist
        """
        # Remove ' init=/usr/lib/raspi-config/init_resize.sh' from cmdline.txt
        pathname = self.abspath(relpath)

        if not os.path.exists(pathname):
            return False

        with open(pathname, "rt") as fd:
            original = fd.read()

        replaced = original.replace(search, replace)
        if replaced == original:
            return False

        with open(pathname, "wt") as fd:
            fd.write(replaced)
        return True

    def copy_if_unchanged(self, src: str, dst_relpath: str) -> bool:
        """
        Copy ``src`` as ``dst_relpath`` inside the chroot, but only if
        ``dst_relpath`` does not exist or is different than ``src``.

        :return: True if the copy happened, False if ``dst_relpath`` was alredy
                 there with the right content
        """
        dest = self.abspath(dst_relpath)
        if os.path.exists(dest):
            # Do not install it twice if it didn't change
            with open(src, "rb") as fd:
                src_contents = fd.read()
            with open(dest, "rb") as fd:
                dst_contents = fd.read()
            if src_contents == dst_contents:
                return False

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            os.unlink(dest)
        shutil.copy(src, dest)
        return True

    def copy_to(self, src: str, dst_relpath: str):
        """
        Copy the given file or directory inside the given path in the chroot.

        The file name will not be changed.
        """
        basename = os.path.basename(src)
        dest = self.abspath(dst_relpath, basename)

        # Remove destination if it exists
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        elif os.path.exists(dest):
            os.unlink(dest)

        if os.path.isdir(src):
            shutil.copytree(src, dest)
        else:
            shutil.copy(src, dest)

    @contextmanager
    def stash_file(self, relpath: str, suffix: Optional[str] = None) -> Iterator[str]:
        """
        Move the given file to a temporary location for the duration of this
        context manager.

        Produces the path to the temporary location.
        """
        abspath = self.abspath(relpath)
        if os.path.lexists(abspath):
            fd, tmppath = tempfile.mkstemp(dir=os.path.dirname(abspath), suffix=suffix)
            os.close(fd)
            os.rename(abspath, tmppath)
        else:
            tmppath = None
        try:
            yield tmppath
        finally:
            if os.path.lexists(abspath):
                os.unlink(abspath)
            if tmppath is not None:
                os.rename(tmppath, abspath)

    @contextmanager
    def working_resolvconf(self):
        """
        Temporarily replace /etc/resolv.conf in the chroot with the current
        system one
        """
        with self.stash_file("/etc/resolv.conf"):
            shutil.copy("/etc/resolv.conf", self.abspath("/etc/resolvconf"))
            yield

    def systemctl_enable(self, unit: str):
        """
        Enable (and if needed unmask) the given systemd unit
        """
        with self.working_resolvconf():
            env = dict(os.environ)
            env["LANG"] = "C"
            subprocess.run(["systemctl", "--root=" + self.root, "enable", unit], check=True, env=env)
            subprocess.run(["systemctl", "--root=" + self.root, "unmask", unit], check=True, env=env)

    def systemctl_disable(self, unit: str, mask=True):
        """
        Disable (and optionally mask) the given systemd unit
        """
        with self.working_resolvconf():
            env = dict(os.environ)
            env["LANG"] = "C"
            subprocess.run(["systemctl", "--root=" + self.root, "disable", unit], check=True, env=env)
            if mask:
                subprocess.run(["systemctl", "--root=" + self.root, "mask", unit], check=True, env=env)

    def run(self, cmd: List[str], check=True, **kw) -> subprocess.CompletedProcess:
        """
        Run the given command inside the chroot
        """
        log.info("%s: running %s", self.root, " ".join(shlex.quote(x) for x in cmd))
        chroot_cmd = ["systemd-nspawn", "-D", self.root]
        chroot_cmd.extend(cmd)
        if "env" not in kw:
            kw["env"] = dict(os.environ)
            kw["env"]["LANG"] = "C"
        with self.working_resolvconf():
            return subprocess.run(chroot_cmd, check=check, **kw)

    def apt_install(self, pkglist: Union[str, List[str]], recommends=False):
        """
        Install the given package(s), if they are not installed yet
        """
        if isinstance(pkglist, str):
            pkglist = [pkglist]

        cmd = ["apt", "-y", "install"]
        if not recommends:
            cmd.append("--no-install-recommends")

        has_packages = False
        for pkg in pkglist:
            if os.path.exists(os.path.join(self.root, "var", "lib", "dpkg", "info", pkg + ".list")):
                continue
            cmd.append(pkg)
            has_packages = True

        if not has_packages:
            return

        self.run(cmd)

    def dpkg_purge(self, pkglist: Union[str, List[str]]):
        """
        Deinstall and purge the given package(s), if they are installed
        """
        if isinstance(pkglist, str):
            pkglist = [pkglist]

        cmd = ["dpkg", "--purge"]
        has_packages = False
        for pkg in pkglist:
            if not os.path.exists(os.path.join(self.root, "var", "lib", "dpkg", "info", pkg + ".list")):
                continue
            cmd.append(pkg)
            has_packages = True

        if not has_packages:
            return

        self.run(cmd)

    def run_actions(self, actions: Sequence[Action]):
        """
        Run a sequence of provisioning actions in the chroot
        """
        for action in actions:
            log.info("%s: running action %s", self.root, action.name)
            action.run(self)

#    def edit_kernel_commandline(self, fname="cmdline.txt"):
#        """
#        Manipulate the kernel command line as an editable list.
#
#        If the list gets changed, it is written back.
#        """
#        dest = self.abspath(fname)
#        with open(dest, "rt") as fd:
#            line = fd.read().strip()
#
#        line_split = line.split()
#        yield line_split
#
#        new_line = " ".join(line_split)
#        if new_line != line:
#            with open(dest, "wt") as fd:
#                print(new_line, file=fd)
#
#    @contextmanager
#    def bind_mount(self, chroot, relpath):
#        run(["mount", "--bind", chroot.root, self.abspath(relpath)])
#        try:
#            yield
#        finally:
#            run(["umount", self.abspath(relpath)])
#
#    @contextmanager
#    def replace_apt_source(self, source, keyring):
#        with self.stash_file("/etc/apt/sources.list"):
#            with self.stash_file("/etc/apt/sources.list.d/raspi.list", suffix=".orig"):
#                with self.stash_file("/etc/apt/trusted.gpg"):
#                    with open(self.abspath("/etc/apt/sources.list"), "wt") as fd:
#                        print(source, file=fd)
#                    if keyring:
#                        shutil.copy(keyring, self.abspath("/etc/apt/trusted.gpg"))
#                    yield
