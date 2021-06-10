from .action import Action
from .namespace import Namespace
from . import facts

builtin = Namespace("builtin")

# Import action modules so they can register with the builtin namespace
from . import file  # noqa
from . import copy  # noqa
from . import blockinfile  # noqa
from . import apt  # noqa
from . import command  # noqa
from . import systemd  # noqa

__all__ = ["Action", "builtin", "facts"]
