from __future__ import annotations
from typing import Dict, Optional, Sequence, Generator, Any, BinaryIO
import collections
import logging
try:
    import mitogen
    import mitogen.core
    import mitogen.master
    import mitogen.service
    import mitogen.parent
except ModuleNotFoundError:
    mitogen = None
from .. import actions
from ..actions import Action
from . import System, Pipeline

log = logging.getLogger(__name__)


if mitogen is None:

    class Mitogen(System):
        def __init__(self, *args, **kw):
            raise NotImplementedError("the mitogen python module is not installed on this system")

else:

    # FIXME: can this be somewhat added to the remote's service pool, and persist across actions?
    class LocalMitogen(System):
        def __init__(self, parent_context: mitogen.core.Context, router: mitogen.core.Router):
            self.parent_context = parent_context
            self.router = router

        def transfer_file(self, src: str, dst: BinaryIO, **kw):
            """
            Fetch file ``src`` from the controller and write it to the open
            file descriptor ``dst``.
            """
            ok, metadata = mitogen.service.FileService.get(
                context=self.parent_context,
                path=src,
                out_fp=dst,
            )
            if not ok:
                raise IOError(f'Transfer of {src!r} was interrupted')

    class MitogenPipeline(Pipeline):
        def __init__(self, system: "Mitogen"):
            self.system = system
            self.chain = mitogen.parent.CallChain(system.context, pipelined=True)

        def add(self, action: Action):
            """
            Add an action to the execution pipeline
            """
            self.system.pending_actions.append(
                self.chain.call_async(Mitogen._remote_run_actions, self.system.router.myself(), action.serialize())
            )

        def reset(self):
            self.chain.reset()

        def close(self):
            self.chain.reset()

    class Mitogen(System):
        """
        Access a system via Mitogen
        """
        internal_broker = None
        internal_router = None

        def __init__(self, name: str, method: str, router: Optional[mitogen.master.Router] = None, **kw):
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

        def share_file(self, pathname: str):
            self.file_service.register(pathname)

        def share_file_prefix(self, pathname: str):
            self.file_service.register_prefix(pathname)

        def create_pipeline(self) -> "Pipeline":
            return MitogenPipeline(self)

        def execute(self, action: actions.Action) -> actions.Action:
            res = self.context.call(self._remote_run_actions, self.router.myself(), action.serialize())
            return Action.deserialize(res)

        def receive_actions(self) -> Generator[actions.Action, None, None]:
            """
            Receive results of the actions that have been sent so far.

            It is ok to enqueue new actions while this method runs
            """
            while self.pending_actions:
                yield Action.deserialize(self.pending_actions.popleft().get().unpickle())

        def run_actions(self, action_list: Sequence[actions.Action]) -> Generator[actions.Action, None, None]:
            """
            Run a sequence of provisioning actions in the chroot
            """
            with self.create_pipeline() as pipe:
                for act in action_list:
                    pipe.add(act)
            yield from self.receive_actions()

        @classmethod
        @mitogen.core.takes_router
        def _remote_run_actions(
                self,
                context: mitogen.core.Context,
                action: Action,
                router: mitogen.core.Router = None) -> Dict[str, Any]:
            system = LocalMitogen(parent_context=context, router=router)
            action = Action.deserialize(action)
            with action.result.collect():
                action.run(system)
            return action.serialize()
