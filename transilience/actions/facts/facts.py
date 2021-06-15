from __future__ import annotations
from typing import Optional, Dict, Any
from dataclasses import dataclass
from ..action import Action


@dataclass
class Facts(Action):
    """
    Collect facts about the system
    """
    pass
