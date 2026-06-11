"""Tool: run_command — execute a shell command.

**MUTATING.** The TUI gates this with a `ModalScreen` confirmation
before the tool actually runs. The tool itself just runs the
command and returns stdout/stderr/exit code.

We deliberately do NOT whitelist commands here. The confirmation
step is the only gate. (The TUI's confirmation screen is in
`screens/confirm.py`.)
"""
from __future__ import annotations

import shlex
import subprocess
import time

from langchain_core.tools import tool

_TIMEOUT_S = 30
_MAX_OUTPUT = 64 * 1024  # 64 KiB per stream


@tool
def run_command(cmd: str) -> str:
    """Run a shell command and return its combined output.

    Use this when the user asks you to do something the other tools
    can't: install a package, restart a service, run a build, etc.
    The TUI will ask the user to confirm before this tool runs.

    Args:
        cmd: A shell command string. Executed via `sh -c`, so pipes,
            redirects, and env var expansion work.

    Returns:
        A multi-line string with:
        - exit_code: the process exit code (0 = success)
        - stdout: up to 64 KiB
        - stderr: up to 64 KiB
        - duration_s: how long the command took

    Returns TIMEOUT if the command exceeds 30s.
    Returns SPAWN_ERROR if the command couldn't be launched.
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["sh", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"TIMEOUT: {cmd!r} exceeded {_TIMEOUT_S}s"
    except FileNotFoundError as e:
        return f"SPAWN_ERROR: {e}"
    except OSError as e:
        return f"SPAWN_ERROR: {e}"

    duration = time.monotonic() - start
    out = proc.stdout[:_MAX_OUTPUT]
    err = proc.stderr[:_MAX_OUTPUT]
    out_truncated = len(proc.stdout) > _MAX_OUTPUT
    err_truncated = len(proc.stderr) > _MAX_OUTPUT

    parts = [
        f"exit_code: {proc.returncode}",
        f"duration_s: {duration:.2f}",
    ]
    if out:
        parts.append("--- stdout ---")
        parts.append(out.rstrip("\n"))
        if out_truncated:
            parts.append(f"... (truncated at {_MAX_OUTPUT} bytes)")
    if err:
        parts.append("--- stderr ---")
        parts.append(err.rstrip("\n"))
        if err_truncated:
            parts.append(f"... (truncated at {_MAX_OUTPUT} bytes)")
    if not out and not err:
        parts.append("(no output)")

    return "\n".join(parts)


def is_dangerous(cmd: str) -> tuple[bool, str]:
    """Heuristic check for obviously destructive commands.

    Returns (True, reason) if the command matches a known-dangerous
    pattern. Used by the TUI's confirmation screen to surface the
    risk to the user.
    """
    tokens = shlex.split(cmd) if cmd.strip() else []
    if not tokens:
        return False, ""

    first = tokens[0].rsplit("/", 1)[-1]  # handle /usr/bin/rm
    if first in {"rm", "mv", "chmod", "chown", "kill", "killall", "pkill", "dd"}:
        return True, f"`{first}` modifies or destroys state"
    if first in {"sudo", "su"}:
        return True, "elevated privileges"
    if first in {"shutdown", "reboot", "halt", "poweroff", "init"}:
        return True, f"`{first}` affects system availability"
    if first in {"mkfs", "fdisk", "parted"}:
        return True, f"`{first}` modifies disk partitions"
    if first == "sh" and "-c" in tokens:
        return False, ""  # covered by other patterns
    if first == "curl" and any(t.startswith("DELETE") or t.startswith("PUT") for t in tokens):
        return True, "HTTP write via curl"
    return False, ""
