"""Strata TUI tools — placeholder set for Phase 0.

In Phase 0 the TUI only proves the chat surface works. The agent
binds to a placeholder ``echo`` tool so the LangChain ``bind_tools``
plumbing is exercised without needing the backend.

From Phase 1 onwards, the tool set will be sourced from MCP
servers in the backend via ``langchain-mcp-adapters``. The shape
of this module stays the same: a ``build_tools()`` factory that
returns a list of LangChain ``BaseTool`` instances.
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def echo(text: str) -> str:
    """Echo a string back. Placeholder tool for Phase 0.

    This will be removed in Phase 1 once real tools (k8s reads via
    MCP) are available.

    Args:
        text: The text to echo.

    Returns:
        The same text.
    """
    return text


def build_tools() -> list:
    """Return the list of tools the TUI agent should bind to."""
    return [echo]