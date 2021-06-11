from __future__ import annotations
from .action import Action
from .namespace import Namespace, builtin

# Import action modules so they can register with the builtin namespace
from . import facts
from . import file  # noqa
from . import copy  # noqa
from . import blockinfile  # noqa
from . import apt  # noqa
from . import command  # noqa
from . import systemd  # noqa
from . import user  # noqa

__all__ = ["Action", "Namespace", "builtin", "facts"]
