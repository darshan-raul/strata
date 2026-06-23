"""Phase 0 placeholder tests for the TUI tool registry.

These tests verify the placeholder ``echo`` tool. Real k8s +
MCP tools land in Phase 1.
"""
from __future__ import annotations

from strata_tui.tools import build_tools, echo


def test_echo_tool_returns_input() -> None:
    assert echo.invoke({"text": "hello"}) == "hello"


def test_build_tools_returns_echo() -> None:
    tools = build_tools()
    assert any(t.name == "echo" for t in tools)