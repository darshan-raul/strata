"""Tool: list a directory.

Read-only. Returns a newline-separated listing with file type
markers, or an error string if the path doesn't exist / isn't
readable.
"""
from __future__ import annotations

import os

from langchain_core.tools import tool


@tool
def list_dir(path: str = ".") -> str:
    """List the contents of a directory.

    Use this when the user asks "what's in /var/log?", "show me the
    files in my home directory", or wants to enumerate a path.

    Args:
        path: Absolute or relative directory path. Defaults to "." (cwd).

    Returns:
        A newline-separated listing. Each line is "TYPE NAME" where
        TYPE is one of: d (dir), f (file), l (symlink), ? (other).
        Hidden files (starting with ".") are included.

    Returns NOT_FOUND if the path doesn't exist.
    Returns NOT_A_DIRECTORY if the path is a file.
    Returns PERMISSION_DENIED if the path isn't readable.
    """
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name)
    except FileNotFoundError:
        return f"NOT_FOUND: {path}"
    except NotADirectoryError:
        return f"NOT_A_DIRECTORY: {path}"
    except PermissionError:
        return f"PERMISSION_DENIED: {path}"

    lines: list[str] = []
    for entry in entries:
        try:
            if entry.is_dir():
                marker = "d"
            elif entry.is_file():
                marker = "f"
            elif entry.is_symlink():
                marker = "l"
            else:
                marker = "?"
        except OSError:
            marker = "?"
        lines.append(f"{marker} {entry.name}")
    return "\n".join(lines) if lines else "(empty directory)"
