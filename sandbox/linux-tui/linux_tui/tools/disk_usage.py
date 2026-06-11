"""Tool: disk usage.

Read-only. Returns human-readable sizes (KiB/MiB/GiB) per mount.
Backed by `shutil.disk_usage`.
"""
from __future__ import annotations

import shutil

from langchain_core.tools import tool


def _human(n: int) -> str:
    """Format a byte count as KiB/MiB/GiB/TiB."""
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.1f} {u}" if u != "B" else f"{int(f)} B"
        f /= 1024
    return f"{f:.1f} TiB"


@tool
def disk_usage(path: str = "/") -> str:
    """Get disk space usage for the filesystem containing `path`.

    Use this when the user asks "how much disk do I have left?",
    "is /var/log full?", or wants to check space on a mount.

    Args:
        path: Any path on the filesystem to check. Defaults to "/".

    Returns:
        A multi-line string with total, used, free, and percent used.
    """
    try:
        usage = shutil.disk_usage(path)
    except FileNotFoundError:
        return f"NOT_FOUND: {path}"
    except PermissionError:
        return f"PERMISSION_DENIED: {path}"

    pct = (usage.used / usage.total) * 100 if usage.total else 0
    return (
        f"path: {path}\n"
        f"total: {_human(usage.total)}\n"
        f"used:  {_human(usage.used)} ({pct:.1f}%)\n"
        f"free:  {_human(usage.free)}"
    )
