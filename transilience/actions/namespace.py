from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Callable

if TYPE_CHECKING:
    from .actions import Action


class Namespace:
    """
    Registry for a group of actions
    """

    def __init__(self, name: str):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Action namespace {self.name!r}"

    def action(
            self,
            factory: Optional[Callable[..., Action]] = None,
            *,
            name=None):
        if factory is None:
            def decorator(factory: Callable[..., Action] = None):
                nonlocal name
                if name is None:
                    name = factory.__name__
                setattr(self, name, factory)
                return factory
            return decorator
        else:
            name = factory.__name__
            setattr(self, name, factory)
            return factory
