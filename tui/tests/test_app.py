"""Strata TUI tests.

The current tests are smoke tests: they verify the App boots,
the LLM initializes, the chat pipeline produces a response, and
``:get`` commands return the Phase 0 placeholder. Real agent
graph + MCP tests land in Phase 1.

Tests use Textual's ``App.run_test`` async harness; no real LLM
network call is made (``FakeListChatModel`` from
``langchain-core`` is wired in by patching
``strata_tui.app.ChatOpenAI``).
"""
from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from textual.widgets import Input

from strata_tui.app import StrataTUIApp
from strata_tui.widgets.history import MessageHistory
from strata_tui.widgets.status_bar import StatusBar


@pytest.fixture
def fake_llm(monkeypatch):
    """Patch ChatOpenAI to return canned responses."""

    def _factory(**_kwargs):
        return FakeListChatModel(responses=["hello from strata"])

    monkeypatch.setattr("strata_tui.app.ChatOpenAI", _factory)


@pytest.mark.asyncio
async def test_app_starts_and_sends_chat(fake_llm) -> None:
    """End-to-end smoke test: type, send, see the AI reply."""
    app = StrataTUIApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#input")
        await pilot.press(*"hi there")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        history = app.query_one("#history", MessageHistory)
        text = history.lines[-1] if history.lines else ""
        assert "hello from strata" in str(text)


@pytest.mark.asyncio
async def test_get_command_returns_placeholder(fake_llm) -> None:
    """``:get pods`` should print the placeholder, no LLM call."""
    app = StrataTUIApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#input")
        await pilot.press(*":get pods")
        await pilot.press("enter")
        await pilot.pause()
        history = app.query_one("#history", MessageHistory)
        all_text = "\n".join(str(line) for line in history.lines)
        assert "not implemented" in all_text.lower()


@pytest.mark.asyncio
async def test_status_bar_shows_model(fake_llm) -> None:
    """Status bar should display the configured model name."""
    app = StrataTUIApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        status = app.query_one("#status", StatusBar)
        assert "MiniMax-M3" in str(status.render())


@pytest.mark.asyncio
async def test_clear_binding_wipes_history(fake_llm) -> None:
    """Ctrl+L should clear the message history."""
    app = StrataTUIApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#input")
        await pilot.press(*"first message")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+l")
        await pilot.pause()
        history = app.query_one("#history", MessageHistory)
        assert history.lines == []
        assert app.query_one("#input", Input) is not None