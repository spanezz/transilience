from __future__ import annotations
from typing import Iterator, Dict
from .utils import run
import re
import os
import logging
import json
import contextlib

log = logging.getLogger(__name__)


class BlockDevice:
    """
    Information and access to a generic block device
    """
    def __init__(self, path: str):
        self.path = path
        self.refresh()


class ImageFile(BlockDevice):
    def refresh(self):
        pass

    @contextlib.contextmanager
    def partitions(self) -> Dict[str, "Partition"]:
        """
        Context manager that create loop devices to access partitions inside the
        image, and shuts them down at the end
        """
        res = run(("kpartx", "-avs", self.path), text=True, capture_output=True)
        devs = {}
        re_mapping = re.compile(r"^add map (\S+)")
        for line in res.stdout.splitlines():
            mo = re_mapping.match(line)
            if not mo:
                log.error("Unrecognised kpartx output line: %r", line)
                continue
            dev = Partition(os.path.join("/dev/mapper", mo.group(1)))
            devs[dev.label] = dev

        try:
            yield devs
        finally:
            res = run(("kpartx", "-ds", self.path))


class Partition(BlockDevice):
    """
    Information and access to a block device for a disk partition
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
