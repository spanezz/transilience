from __future__ import annotations
from typing import Dict, Optional, Sequence, Generator, Any, BinaryIO, ContextManager
import collections
import contextlib
import threading
import logging
import uuid
import io
try:
    import mitogen
    import mitogen.core
    import mitogen.master
    import mitogen.service
    import mitogen.parent
except ModuleNotFoundError:
    mitogen = None
from .. import actions
from ..actions.action import FileAsset, LocalFileAsset, ZipFileAsset
from .system import System, PipelineInfo
from .pipeline import LocalPipelineMixin
from .local import LocalExecuteMixin

log = logging.getLogger(__name__)

_this_system_lock = threading.Lock()
_this_system = None


if mitogen is None:

    class Mitogen(System):
        def __init__(self, *args, **kw):
            raise NotImplementedError("the mitogen python module is not installed on this system")

else:
    class MitogenCachedFileAsset(FileAsset):
        def __init__(self, cached: bytes, serialized: Dict[str, Any]):
            super().__init__()
            self.cached = cached
            self.serialized = serialized

        def serialize(self) -> Dict[str, Any]:
            return self.serialized

        @contextlib.contextmanager
        def open(self) -> ContextManager[BinaryIO]:
            with io.BytesIO(self.cached) as buf:
                yield buf

        def copy_to(self, dst: BinaryIO):
            dst.write(self.cached)

    class MitogenFileAsset(FileAsset):
        def __init__(self, local_mitogen: "LocalMitogen", remote_path: str):
            super().__init__()
            self.local_mitogen = local_mitogen
            self.remote_path = remote_path

        def serialize(self) -> Dict[str, Any]:
            res = super().serialize()
            res["type"] = "local"
            res["path"] = self.remote_path
            return res

        @contextlib.contextmanager
        def open(self) -> ContextManager[BinaryIO]:
            with io.BytesIO() as buf:
                self.copy_to(buf)
                buf.seek(0)
                yield buf

        def copy_to(self, dst: BinaryIO):
            ok, metadata = mitogen.service.FileService.get(
                context=self.local_mitogen.parent_context,
                path=self.remote_path,
                out_fp=dst,
            )
            if not ok:
                raise IOError(f'Transfer of {self.path!r} was interrupted')

    class LocalMitogen(LocalExecuteMixin, LocalPipelineMixin, System):
        def __init__(self, parent_context: mitogen.core.Context, router: mitogen.core.Router):
            super().__init__("local_mitogen")
            self.parent_context = parent_context
            self.router = router

        def remap_file_asset(self, asset: FileAsset):
            if asset.cached is not None:
                return MitogenCachedFileAsset(asset.cached, asset.serialize())
            elif isinstance(asset, LocalFileAsset):
                return MitogenFileAsset(self, asset.path)
            # elif isinstance(asset, ZipFileAsset):
            #     return MitogenZipFileAsset(self, asset.archive, asset.path)
            else:
                raise NotImplementedError(f"Unable to handle File asset of type {asset.__class__!r}")

    class Mitogen(System):
        """
        Access a system via Mitogen
        """
        internal_broker = None
        internal_router = None

        def __init__(self, name: str, method: str, router: Optional[mitogen.master.Router] = None, **kw):
            super().__init__(name)
            if router is None:
                if self.internal_router is None:
                    self.internal_broker = mitogen.master.Broker()
                    self.internal_router = mitogen.master.Router(self.internal_broker)
                router = self.internal_router
            self.router = router
            self.file_service = mitogen.service.FileService(router)
            self.pool = mitogen.service.Pool(router=self.router, services=[self.file_service])

            meth = getattr(self.router, method, None)
            if meth is None:
                raise KeyError(f"conncetion method {method!r} not available in mitogen")

            kw.setdefault("python_path", "/usr/bin/python3")
            self.context = meth(remote_name=name, **kw)

            self.pending_actions = collections.deque()

        def close(self):
            self.context.shutdown(wait=True)

        def share_file(self, pathname: str):
            self.file_service.register(pathname)

        def share_file_prefix(self, pathname: str):
            self.file_service.register_prefix(pathname)

        def execute(self, action: actions.Action) -> actions.Action:
            res = self.context.call(self._remote_run_actions, self.router.myself(), action.serialize())
            return actions.Action.deserialize(res)

        def send_pipelined(self, action: actions.Action, pipeline_info: PipelineInfo):
            """
            Execute this action as part of a pipeline
            """
            serialized = action.serialize()
            serialized["__pipeline__"] = pipeline_info.serialize()
            self.pending_actions.append(
                self.context.call_async(self._remote_run_actions, self.router.myself(), serialized)
            )

        def receive_pipelined(self) -> Generator[actions.Action, None, None]:
            """
            Receive results of the actions that have been sent so far.

            It is ok to enqueue new actions while this method runs
            """
            while self.pending_actions:
                yield actions.Action.deserialize(self.pending_actions.popleft().get().unpickle())

        def pipeline_clear_failed(self, pipeline_id: str):
            self.context.call_no_reply(self._pipeline_clear_failed, pipeline_id)

        def pipeline_close(self, pipeline_id: str):
            self.context.call_no_reply(self._pipeline_close, pipeline_id)

        def run_actions(self, action_list: Sequence[actions.Action]) -> Generator[actions.Action, None, None]:
            """
            Run a sequence of provisioning actions in the chroot
            """
            pipeline = PipelineInfo(str(uuid.uuid4()))
            for act in action_list:
                self.send_pipelined(act, pipeline)
            yield from self.receive_pipelined()

        @classmethod
        def _pipeline_clear_failed(cls, pipeline_id: str):
            global _this_system, _this_system_lock
            with _this_system_lock:
                if _this_system is None:
                    return
                system = _this_system
            system.pipeline_clear_failed(pipeline_id)

        @classmethod
        def _pipeline_close(self, pipeline_id: str):
            global _this_system, _this_system_lock
            with _this_system_lock:
                if _this_system is None:
                    return
                system = _this_system
            system.pipeline_close(pipeline_id)

        @classmethod
        @mitogen.core.takes_router
        def _remote_run_actions(
                self,
                context: mitogen.core.Context,
                action: actions.Action,
                router: mitogen.core.Router = None) -> Dict[str, Any]:

            global _this_system, _this_system_lock
            with _this_system_lock:
                if _this_system is None:
                    _this_system = LocalMitogen(parent_context=context, router=router)
                system = _this_system

            pipeline_info = action.pop("__pipeline__", None)

            # Convert LocalFileAsset to something that fetches via Mitogen
            file_assets = action.get("__file_assets__", None)
            if file_assets is None:
                file_assets = []

            action = actions.Action.deserialize(action)
            for name in file_assets:
                setattr(action, name,
                        system.remap_file_asset(
                            getattr(action, name)))

            if pipeline_info is None:
                action = system.execute(action)
            else:
                pipeline = PipelineInfo.deserialize(pipeline_info)
                action = system.execute_pipelined(action, pipeline)
            return action.serialize()
