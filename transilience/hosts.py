from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Any
from dataclasses import dataclass, field
import transilience.system


if TYPE_CHECKING:
    from transilience.system import System


@dataclass
class Host:
    name: str
    type: str = "Mitogen"
    args: Dict[str, Any] = field(default_factory=dict)

    def _make_system(self) -> System:
        cls = getattr(transilience.system, self.type)
        return cls(self.name, **self.args)
