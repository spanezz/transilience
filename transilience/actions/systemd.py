from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass
import subprocess
import shutil
import shlex
import os
from .action import Action
from . import builtin

if TYPE_CHECKING:
    import transilience.system


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/systemd_module.html
@builtin.action(name="systemd")
@dataclass
class Systemd(Action):
    """
    Same as ansible's builtin.systemd.
    """
    scope: str = "system"
    no_block: bool = False
    force: bool = False
    daemon_reexec: bool = False
    daemon_reload: bool = False
    unit: Optional[str] = None
    enabled: Optional[bool] = None
    masked: Optional[bool] = None
    state: Optional[str] = None

    def summary(self):
        summary = ""

        if self.unit is not None:
            verbs = []
            if self.masked is not None:
                verbs.append("mask")

            if self.enabled is not None:
                verbs.append("enable")

            if self.state == "started":
                verbs.append("start")
            elif self.state == "stopped":
                verbs.append("stop")
            elif self.state == "reloaded":
                verbs.append("reload")
            elif self.state == "restarted":
                verbs.append("restart")

            if verbs:
                summary = ", ".join(verbs) + " " + self.unit

        verbs = []
        if self.daemon_reload:
            verbs.append("reload")
        if self.daemon_reexec:
            verbs.append("restart")

        if verbs:
            if summary:
                summary += " and "
            summary += " and ".join(summary, ", ".join(verbs) + " systemd")

        if not summary:
            summary += "systemd action with nothing to do"

        if self.scope != "system":
            summary += f" [{self.scope} scope]"

        return summary

    def run(self, system: transilience.system.System):
        super().run(system)

        systemctl = shutil.which("systemctl")
        if systemctl is None:
            raise RuntimeError("systemctl not found")

        cmd = [systemctl]

        if self.scope != "system":
            cmd.append(f"--{self.scope}")

        if self.no_block:
            cmd.append("--no-block")

        if self.force:
            cmd.append("--force")

        env = dict(os.environ)
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.geteuid()}"

        def run_systemctl(*args, **kw):
            """
            Run systemctl with logging and common subprocess args
            """
            kw.setdefault("env", env)
            kw.setdefault("check", True)
            kw.setdefault("capture_output", True)
            systemctl_cmd = cmd + list(args)
            formatted_cmd = " ".join(shlex.quote(x) for x in systemctl_cmd)
            self.log.info("running %s", formatted_cmd)
            try:
                return subprocess.run(systemctl_cmd, **kw)
            except subprocess.CalledProcessError as e:
                self.log.error("%s: exited with code %d and stderr %r", formatted_cmd, e.returncode, e.stderr)
                raise

        if self.daemon_reload:
            run_systemctl("daemon-reload")

        if self.daemon_reexec:
            run_systemctl("daemon-reexec")

        if self.unit is not None:
            # Fetch the current status of the unit
            # Documentation of UnitFileState values can be found in man systemctl(1)
            res = run_systemctl("show", self.unit, "--no-page", check=False, text=True)

            unit_info = {}
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    k, v = line.strip().split("=", 1)
                    unit_info[k] = v

            if self.masked is not None:
                orig_masked = unit_info.get("UnitFileState") == "masked"
                if self.masked != orig_masked:
                    run_systemctl("mask" if self.masked else "unmask", self.unit)
                    self.set_changed()

            if self.enabled is not None:
                orig_enabled = unit_info.get("UnitFileState") in (
                        "enabled", "enabled-runtime", "alias", "static",
                        "indirect", "generated", "transient")
                if self.enabled != orig_enabled:
                    run_systemctl("enable" if self.enabled else "disable", self.unit)
                    self.set_changed()

            if self.state is not None:
                action = None
                cur_state = unit_info.get("ActiveState")
                # self.log.info("ActiveState pre: %r", cur_state)
                if cur_state is not None:
                    if self.state == "started":
                        if cur_state not in ("active", "activating"):
                            action = "start"
                    elif self.state == "stopped":
                        if cur_state in ("active", "activating", "deactivating"):
                            action = "stop"
                    elif self.state == "reloaded":
                        if cur_state not in ("active", "activating"):
                            action = "start"
                        else:
                            action = "reload"
                    elif self.state == "restarted":
                        if cur_state not in ("active", "activating"):
                            action = "start"
                        else:
                            action = "restart"

                if action is not None:
                    run_systemctl(action, self.unit)
                    self.set_changed()
