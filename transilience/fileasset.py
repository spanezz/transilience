from __future__ import annotations
from typing import Dict, Any, Optional, BinaryIO, ContextManager
import contextlib
import hashlib
import zipfile
import shutil


class FileAsset:
    """
    Generic interface for local file assets used by actions
    """
    def __init__(self):
        # Cached contents of the file, if it's small
        self.cached: Optional[bytes] = None

    def serialize(self) -> Dict[str, Any]:
        res = {}
        if self.cached is not None:
            res["cached"] = self.cached
        return res

    @contextlib.contextmanager
    def open(self) -> ContextManager[BinaryIO]:
        raise NotImplementedError(f"{self.__class__}.open is not implemented")

    def copy_to(self, dst: BinaryIO):
        with self.open() as src:
            shutil.copyfileobj(src, dst)

    def sha1sum(self) -> str:
        """
        Return the sha1sum of the file contents.

        If the file is small, cache its contents
        """
        h = hashlib.sha1()
        size = 0
        to_cache = []
        with self.open() as fd:
            while True:
                buf = fd.read(40960)
                if not buf:
                    break
                size += len(buf)
                if size > 16384:
                    to_cache = None
                else:
                    to_cache.append(buf)
                h.update(buf)

            if to_cache is not None:
                self.cached = b"".join(to_cache)

            return h.hexdigest()

    @classmethod
    def compute_file_sha1sum(self, fd: BinaryIO) -> str:
        h = hashlib.sha1()
        while True:
            buf = fd.read(40960)
            if not buf:
                break
            h.update(buf)
        return h.hexdigest()

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "FileAsset":
        t = data.get("type")
        cached = data.get("cached")
        if t == "local":
            res = LocalFileAsset(data["path"])
            res.cached = cached
            return res
        elif t == "zip":
            res = ZipFileAsset(data["archive"], data["path"])
            res.cached = cached
            return res
        else:
            raise ValueError(f"Unknown file asset type {t!r}")


class LocalFileAsset(FileAsset):
    """
    FileAsset referring to a local file
    """
    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def serialize(self) -> Dict[str, Any]:
        res = super().serialize()
        res["type"] = "local"
        res["path"] = self.path
        return res

    @contextlib.contextmanager
    def open(self) -> ContextManager[BinaryIO]:
        with open(self.path, "rb") as fd:
            yield fd


class ZipFileAsset(FileAsset):
    """
    FileAsset referencing a file inside a zipfile
    """
    def __init__(self, archive: str, path: str):
        super().__init__()
        self.archive = archive
        self.path = path

    def serialize(self) -> Dict[str, Any]:
        res = super().serialize()
        res["type"] = "zip"
        res["archive"] = self.archive
        res["path"] = self.path
        return res

    @contextlib.contextmanager
    def open(self) -> ContextManager[BinaryIO]:
        with zipfile.ZipFile(self.archive, "r") as zf:
            with zf.open(self.path) as fd:
                yield fd
