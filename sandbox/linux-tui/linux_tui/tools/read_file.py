"""Tool: read a file's contents (head or tail).

Read-only. Returns the first `max_lines` lines by default; pass
`from_end=True` to get the last N lines instead. Large files are
truncated.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

from langchain_core.tools import tool

_MAX_BYTES = 256 * 1024  # 256 KiB hard cap to keep prompts sane


@tool
def read_file(path: str, max_lines: int = 200, from_end: bool = False) -> str:
    """Read the contents of a text file.

    Use this when the user asks "show me /etc/hosts", "what's in
    this config?", "tail the log", or wants to see a file's contents.

    Args:
        path: Absolute or relative file path.
        max_lines: Maximum number of lines to return. Defaults to 200.
            The file is hard-capped at 256 KiB regardless of this.
        from_end: If True, return the last `max_lines` lines instead
            of the first. Use this for logs.

    Returns:
        The file's contents as a string. Lines are joined with "\\n".
        Trailing newline is stripped.

    Returns NOT_FOUND if the path doesn't exist.
    Returns NOT_A_FILE if the path is a directory.
    Returns TOO_LARGE if the file exceeds 256 KiB (and the path).
    Returns DECODE_ERROR if the file isn't UTF-8.
    """
    p = Path(path)
    if not p.exists():
        return f"NOT_FOUND: {path}"
    if not p.is_file():
        return f"NOT_A_FILE: {path}"

    try:
        size = p.stat().st_size
        if size > _MAX_BYTES:
            return f"TOO_LARGE: {path} is {size} bytes (> {_MAX_BYTES} cap)"

        if from_end:
            with p.open("rb") as f:
                tail = deque(f, maxlen=max_lines)
            text = b"".join(tail).decode("utf-8", errors="replace")
        else:
            with p.open("rb") as f:
                raw = f.readline()
                lines: list[bytes] = []
                while raw and len(lines) < max_lines:
                    lines.append(raw)
                    raw = f.readline()
            text = b"".join(lines).decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return f"DECODE_ERROR: {path} is not UTF-8 (probably binary)"
    except PermissionError:
        return f"PERMISSION_DENIED: {path}"

    return text.rstrip("\n")
