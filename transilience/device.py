from __future__ import annotations
from typing import Iterator
from .utils import run
import logging
import json
import contextlib

log = logging.getLogger(__name__)


class Partition:
    """
    Information and access to a block device
    """
    def __init__(self, path: str):
        self.path = path
        self.refresh()

    def refresh(self):
        """
        Update device information from lsblk
        """
        info = run(("lsblk", "--json", "--output-all", "--bytes", self.path), capture_output=True)
        info = json.loads(info.stdout)["blockdevices"][0]
        self.label = info.get("label")
        self.fstype = info.get("fstype")

    @contextlib.contextmanager
    def ext4_dir_index_workaround(self) -> Iterator[None]:
        """
        Temporarily disable dir_index of the ext4 filesystem to work around the
        issue at https://lkml.org/lkml/2018/12/27/155.

        See https://www.enricozini.org/blog/2019/himblick/ext4-and-32bit-arm-on-64bit-amd64/
        """
        if self.fstype != "ext4":
            yield
            return

        log.info("%s: disabling dir_index to workaround https://lkml.org/lkml/2018/12/27/155", self.path)
        run(("tune2fs", "-O", "^dir_index", self.path))

        try:
            yield
        finally:
            log.info("%s: reenabling dir_index", self.path)
            run(("tune2fs", "-O", "dir_index", self.path))
            log.info("%s: running e2fsck to reindex directories", self.path)
            run(("e2fsck", "-fy", self.path))

    @contextlib.contextmanager
    def mount(self, path, *args) -> Iterator[None]:
        """
        Mount this device on the given path for the duration of the context
        manager
        """
        run(("mount", self.path, path, *args))
        try:
            yield
        finally:
            run(("umount", path))
