"""Tool: system info — uname, hostname, OS release.

Read-only. Single-line summary. The LLM uses this when the user
asks "what machine am I on?" or "what OS is this?".
"""
from __future__ import annotations

import os
import platform
import socket

from langchain_core.tools import tool


@tool
def system_info() -> str:
    """Get basic system information: hostname, OS, kernel, arch.

    Use this when the user asks what machine they're on, what the
    OS is, or needs to know the host for context.

    Returns:
        A multi-line string with hostname, OS, kernel, and arch.
    """
    return (
        f"hostname: {socket.gethostname()}\n"
        f"os: {platform.system()} {platform.release()}\n"
        f"kernel: {platform.version()}\n"
        f"arch: {platform.machine()}\n"
        f"python: {platform.python_version()}\n"
        f"cwd: {os.getcwd()}"
    )
