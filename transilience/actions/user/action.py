from __future__ import annotations
from typing import TYPE_CHECKING, Optional
import platform
import shlex
from .. import builtin

if TYPE_CHECKING:
    from . import backend


@builtin.action(name="user")
def instantiate_user_action(*args, **kw) -> backend.User:
    system = platform.system()
    if system == "Linux":
        distribution: Optional[str]
        try:
            with open("/etc/os-release", "rt") as fd:
                for line in fd:
                    k, v = line.split("=", 1)
                    if k == "ID":
                        distribution = shlex.split(v)[0]
                        break
                else:
                    distribution = None
        except FileNotFoundError:
            distribution = None

        if distribution == "alpine":
            from . import linux
            return linux.Alpine(*args, **kw)
        else:
            from . import backend
            return backend.User(*args, **kw)
    if system in ('FreeBSD', 'DragonFly'):
        from . import freebsd
        return freebsd.User(*args, **kw)
    else:
        raise NotImplementedError(f"User backend for {system!r} platform is not available")
