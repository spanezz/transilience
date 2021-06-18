from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, Callable, BinaryIO, List
from dataclasses import dataclass, field, asdict
import threading

if TYPE_CHECKING:
    from ..actions import Action


@dataclass
class PipelineInfo:
    """
    Metadata to control the pipelined execution of an action
    """
    id: str
    # Execute only when the state of all the given actions previous executed in
    # the same pipeline (identified by uuid) is one of those listed
    when: Dict[str, List[str]] = field(default_factory=dict)

    def serialize(self) -> Dict[str, Any]:
        """
        Serialize this pipeline metadata as a dict
        """
        return asdict(self)

    @classmethod
    def deserialize(cls, serialized: Dict[str, Any]) -> "PipelineInfo":
        """
        Deserialize pipeline metadata form a dict
        """
        return cls(**serialized)


class System:
    """
    Access a system to be provisioned
    """
    def __init__(self, name: str):
        self.name = name
        # Objects that can be registered by actions as caches
        self.caches: Dict[Type[Action], Any] = {}
        self.caches_lock = threading.Lock()

    def close(self):
        """
        Close the connection to this system
        """
        pass

    def get_action_cache(self, action: Type[Action], default_factory: Callable[[], Any]):
        """
        Lookup the registered cache for this action.

        If not found, creates it as the result of default_factory
        """
        with self.caches_lock:
            res = self.caches.get(action)
            if res is None:
                res = default_factory()
                self.caches[action] = res
            return res

    def share_file(self, pathname: str):
        """
        Register a pathname as exportable to children
        """
        pass

    def share_file_prefix(self, pathname: str):
        """
        Register a pathname prefix as exportable to children
        """
        pass

    def execute(self, action: Action) -> Action:
        """
        Execute an action immediately.

        For remote systems, this may have serious latency issues, since it
        requires a full round trip for each action that gets executed
        """
        raise NotImplementedError(f"{self.__class__}.execute is not implemented")

    def transfer_file(self, src: str, dst: BinaryIO, **kw):
        """
        Fetch file ``src`` from the controller and write it to the open
        file descriptor ``dst``.
        """
        raise NotImplementedError(f"{self.__class__}.transfer_file is not implemented")
