from __future__ import annotations
from typing import Sequence
import logging
import contextlib
import subprocess
import shlex
import os
import tempfile

log = logging.getLogger(__name__)


def run(cmd: Sequence[str], check: bool = True, **kw) -> subprocess.CompletedProcess:
    """
    Logging wrapper to subprocess.run.

    Also, default check to True.
    """
    log.info("Run %s", " ".join(shlex.quote(x) for x in cmd))
    return subprocess.run(cmd, check=check, **kw)


@contextlib.contextmanager
def atomic_writer(
        fname: str,
        mode: str = "w+b",
        chmod: int = 0o664,
        sync: bool = True,
        use_umask: bool = False,
        **kw):
    """
    open/tempfile wrapper to atomically write to a file, by writing its
    contents to a temporary file in the same directory, and renaming it at the
    end of the block if no exception has been raised.

    :arg fname: name of the file to create
    :arg mode: passed to mkstemp/open
    :arg chmod: permissions of the resulting file
    :arg sync: if True, call fdatasync before renaming
    :arg use_umask: if True, apply umask to chmod

    All the other arguments are passed to open
    """

    if use_umask:
        cur_umask = os.umask(0)
        os.umask(cur_umask)
        chmod &= ~cur_umask

    dirname = os.path.dirname(fname)
    if not os.path.isdir(dirname):
        os.makedirs(dirname)

    fd, abspath = tempfile.mkstemp(dir=dirname, text="b" not in mode, prefix=fname)
    outfd = open(fd, mode, closefd=True, **kw)
    try:
        yield outfd
        outfd.flush()
        if sync:
            os.fdatasync(fd)
        os.fchmod(fd, chmod)
        os.rename(abspath, fname)
    except Exception:
        os.unlink(abspath)
        raise
    finally:
        outfd.close()
