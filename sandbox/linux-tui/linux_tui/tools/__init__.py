"""Linux helper tools, all `@tool`-decorated.

The shape contract:
- Read-only tools: return a `str` directly. The LLM sees the string.
- Mutating tools (`run_command`): same shape, but the TUI gates
  execution with a `ModalScreen` confirmation before the tool runs.

Each tool's docstring is the API the LLM sees. Keep them tight,
with a "Use this when..." clause.
"""
from langchain_core.tools import BaseTool

from linux_tui.tools.disk_usage import disk_usage
from linux_tui.tools.grep import grep
from linux_tui.tools.list_dir import list_dir
from linux_tui.tools.read_file import read_file
from linux_tui.tools.run_command import run_command
from linux_tui.tools.system_info import system_info

ALL_TOOLS: list[BaseTool] = [
    list_dir,
    read_file,
    grep,
    system_info,
    disk_usage,
    run_command,
]

READ_ONLY_TOOLS: list[BaseTool] = [
    list_dir,
    read_file,
    grep,
    system_info,
    disk_usage,
]

MUTATING_TOOLS: set[str] = {"run_command"}

__all__ = [
    "ALL_TOOLS",
    "READ_ONLY_TOOLS",
    "MUTATING_TOOLS",
    "list_dir",
    "read_file",
    "grep",
    "system_info",
    "disk_usage",
    "run_command",
]
