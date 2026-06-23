"""The Textual app: top-level layout, bindings, event wiring.

Phase 0 scope: prove the chat surface works. The agent loop is a
plain LangChain ``ChatOpenAI`` call (no tools bound yet). Phase 1
will introduce the LangGraph ``StateGraph`` and the MCP-backed
tools.

From Phase 1 onwards the agent loop will be a LangGraph graph
whose tools are MCP servers in the backend. The UI (this module)
does not change.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Header, Input

from strata_tui.config import load_settings
from strata_tui.widgets.history import MessageHistory
from strata_tui.widgets.status_bar import StatusBar

SYSTEM_PROMPT = (
    "You are Strata, an AI co-pilot for managing Kubernetes clusters. "
    "Phase 0 placeholder: real tools and backend land in Phase 1+."
)


class StrataTUIApp(App):
    """The Strata TUI application."""

    CSS_PATH = None
    TITLE = "Strata"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._llm: ChatOpenAI | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield MessageHistory(id="history")
            yield Input(placeholder="Ask Strata…", id="input")
            yield StatusBar(id="status")

    def on_mount(self) -> None:
        self.query_one("#status", StatusBar).set_model(self._settings.model)
        try:
            self._llm = ChatOpenAI(
                model=self._settings.model,
                base_url=self._settings.base_url,
                api_key=self._settings.api_key,
                temperature=self._settings.temperature,
            )
        except Exception as exc:  # noqa: BLE001
            self._history().append_error(f"LLM init failed: {exc}")

    def _history(self) -> MessageHistory:
        return self.query_one("#history", MessageHistory)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.query_one("#input", Input).value = ""
        self._history().append_user(text)
        if text.startswith(":get"):
            self._history().append_ai(
                "(placeholder) :get commands are not implemented yet. "
                "Backend lands in Phase 1."
            )
            return
        self._run_turn(text)

    @work(thread=True, exclusive=True)
    def _run_turn(self, text: str) -> None:
        assert self._llm is not None

        status = self.query_one("#status", StatusBar)
        self.call_from_thread(status.set_busy, True)
        try:
            messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=text)]
            response = self._llm.invoke(messages)
            self.call_from_thread(self._history().append_ai, response.content)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._history().append_error, f"LLM call failed: {exc}")
        finally:
            self.call_from_thread(status.set_busy, False)

    def action_clear(self) -> None:
        self._history().clear()