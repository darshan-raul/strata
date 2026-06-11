"""Tool: grep — search for a pattern in a path.

Read-only. Wraps Python's `re` (no shell, no ripgrep dependency).
Returns matches as `path:line_no:line_text`. If `recursive` is
true, walks the directory tree; otherwise searches files directly.
"""
from __future__ import annotations

import re
from pathlib import Path

from langchain_core.tools import tool

_MAX_MATCHES = 200


@tool
def grep(
    pattern: str,
    path: str = ".",
    recursive: bool = True,
    ignore_case: bool = False,
) -> str:
    """Search for a regex pattern in a file or directory.

    Use this when the user asks "find files containing X",
    "where is Y configured?", "grep for foo in /etc", etc.

    Args:
        pattern: A Python regex. To search for a literal string,
            escape special characters (e.g. `\\.log$` for `.log$`).
        path: File or directory to search. Defaults to ".".
        recursive: If path is a directory, walk subdirectories.
            Defaults to True.
        ignore_case: Case-insensitive match. Defaults to False.

    Returns:
        Lines that match, formatted as "path:line_no:line_text".
        Capped at 200 matches. Binary files are skipped.

    Returns NO_MATCHES if nothing matched.
    Returns BAD_PATTERN if the regex doesn't compile.
    """
    try:
        flags = re.IGNORECASE if ignore_case else 0
        compiled = re.compile(pattern, flags=flags)
    except re.error as e:
        return f"BAD_PATTERN: {e}"

    p = Path(path)
    if not p.exists():
        return f"NOT_FOUND: {path}"

    files: list[Path]
    if p.is_file():
        files = [p]
    elif recursive:
        files = [f for f in p.rglob("*") if f.is_file()]
    else:
        files = [f for f in p.glob("*") if f.is_file()]

    out: list[str] = []
    for f in files:
        try:
            with f.open("rb") as fh:
                for i, raw in enumerate(fh, start=1):
                    if len(out) >= _MAX_MATCHES:
                        break
                    try:
                        line = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue  # skip binary
                    if compiled.search(line):
                        out.append(f"{f}:{i}:{line.rstrip()}")
        except (PermissionError, OSError):
            continue
        if len(out) >= _MAX_MATCHES:
            break

    if not out:
        return f"NO_MATCHES for {pattern!r} in {path}"
    suffix = ""
    if len(out) >= _MAX_MATCHES:
        suffix = f"\n... (truncated at {_MAX_MATCHES} matches)"
    return "\n".join(out) + suffix
