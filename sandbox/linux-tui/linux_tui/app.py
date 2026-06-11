"""The Textual app: top-level layout, bindings, event wiring.

Layout:
    ┌────────────────────────────────────┐
    │  Header                            │
    ├────────────────────────────────────┤
    │                                    │
    │  MessageHistory (RichLog)          │
    │                                    │
    ├────────────────────────────────────┤
    │  InputBox (Input, single-line)     │
    ├────────────────────────────────────┤
    │  StatusBar                         │
    └────────────────────────────────────┘

Bindings:
    Enter          send the current input
    Ctrl+C         quit
    Ctrl+L         clear history
    Ctrl+R         toggle raw/parsed output (debug)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any

from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Header
from textual.widgets._input import Input as _Input  # for the Submitted message

from linux_tui.agent.chain import build_chain
from linux_tui.agent.loop import run_turn, tools_to_dict
from linux_tui.agent.model import build_chat_model
from linux_tui.screens.confirm import ConfirmScreen
from linux_tui.tools import ALL_TOOLS
from linux_tui.widgets.history import MessageHistory
from linux_tui.widgets.input_box import InputBox
from linux_tui.widgets.status_bar import StatusBar

log = logging.getLogger("linux-tui.app")


class LinuxTUIApp(App):
    """The TUI Linux helper."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #history-container {
        height: 1fr;
    }
    MessageHistory {
        height: 1fr;
        border: solid $primary;
    }
    InputBox {
        height: 5;
        border: solid $secondary;
    }
    StatusBar {
        height: 1;
        background: $boost;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("ctrl+r", "toggle_raw", "Raw", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._llm: ChatOpenAI | None = None
        self._chain: Runnable | None = None
        self._tools_by_name: dict[str, Any] = {}
        self._history: list = []
        self._raw_output: bool = False  # Ctrl+R toggle
        self._streaming_response: str = ""  # accumulated streamed text
        self._input_lock = threading.Lock()
        self._confirm_event: asyncio.Event | None = None
        self._confirm_result: bool = False

    # ---- layout -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="history-container"):
            yield MessageHistory(id="history")
        yield InputBox(id="input", placeholder="Ask about the local Linux box...")
        yield StatusBar(model_name=os.environ.get("MINIMAX_MODEL", "MiniMax-M3"))

    def on_mount(self) -> None:
        # Build the model and chain. If MINIMAX_API_KEY is missing,
        # log a clear error and quit gracefully.
        try:
            self._llm = build_chat_model()
            self._chain = build_chain(self._llm, ALL_TOOLS)
            self._tools_by_name = tools_to_dict(ALL_TOOLS)
        except RuntimeError as e:
            history = self.query_one(MessageHistory)
            history.append_error(str(e))
            history.append_info("Set MINIMAX_API_KEY in .env, then restart.")
            return

        history = self.query_one(MessageHistory)
        history.append_info(f"Ready. Model: {os.environ.get('MINIMAX_MODEL', 'MiniMax-M3')}")
        history.append_info("Ask me about the local Linux box. Mutating commands ask for confirmation.")
        history.append_info("")

        # Focus the input box.
        self.query_one(InputBox).focus()

    # ---- input handling ---------------------------------------------------

    @on(_Input.Submitted)
    def on_input_submitted(self, event: _Input.Submitted) -> None:
        """Fired by InputBox when the user presses Enter."""
        text = (event.value or "").strip()
        if not text:
            return
        # Clear the input box. The Input widget exposes `.value`.
        input_box = self.query_one(InputBox)
        input_box.value = ""

        # Run the agent turn on a worker so the UI stays responsive.
        self._run_user_turn(text)

    @work(exclusive=True, thread=True)
    def _run_user_turn(self, user_text: str) -> None:
        """Background worker: runs the agent loop and posts events.

        Streamed AI tokens are surfaced via a callback the loop calls
        per token. We post them onto the main thread via
        `app.call_from_thread`.
        """
        history = self.query_one(MessageHistory)
        status = self.query_one(StatusBar)
        input_box = self.query_one(InputBox)

        with self._input_lock:
            self.call_from_thread(history.append_user, user_text)
            self.call_from_thread(status.set_busy, True)
            self.call_from_thread(setattr, input_box, "disabled", True)

            def on_tool_call(name: str, args: dict) -> None:
                self.call_from_thread(history.append_tool_call, name, args)

            def on_tool_result(name: str, content: str) -> None:
                self.call_from_thread(history.append_tool_result, name, content)

            def on_iteration(_n: int) -> None:
                # If we're using a non-streaming model, the chunks
                # callback never fires; this is the only signal that
                # the agent is "thinking."
                pass

            def is_mutating_allowed(name: str, args: dict) -> bool:
                # Ask the main thread to show a modal and wait for
                # the user's response.
                fut: asyncio.Future[bool] = asyncio.run_coroutine_threadsafe(
                    self._ask_confirm(name, args),
                    self._main_loop,  # type: ignore[attr-defined]
                )
                return fut.result()

            try:
                msgs, final_ai = run_turn(
                    self._chain,
                    self._tools_by_name,
                    user_text,
                    history=self._history,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                    on_iteration=on_iteration,
                    is_mutating_allowed=is_mutating_allowed,
                )
                self._history = msgs
                final_text = final_ai.content if isinstance(final_ai, AIMessageChunk) else (
                    final_ai.content if hasattr(final_ai, "content") else str(final_ai)
                )
                if final_text:
                    if self._raw_output:
                        self.call_from_thread(history.append_info, repr(final_ai))
                    self.call_from_thread(history.append_ai, final_text)
            except Exception as e:
                log.exception("turn failed")
                self.call_from_thread(history.append_error, f"{type(e).__name__}: {e}")
            finally:
                self.call_from_thread(status.set_busy, False)
                self.call_from_thread(setattr, input_box, "disabled", False)
                self.call_from_thread(input_box.focus)

    async def _ask_confirm(self, tool_name: str, args: dict) -> bool:
        """Show the confirmation modal and await the user's choice.

        Runs on the main event loop. Returns True if allowed.
        """
        result_holder: list[bool | None] = [None]
        event = asyncio.Event()

        def on_dismiss(result: bool | None) -> None:
            result_holder[0] = bool(result) if result is not None else False
            event.set()

        screen = ConfirmScreen(tool_name, args)
        # When dismissed, `on_dismiss` is called with the result.
        self.push_screen(screen, on_dismiss)
        await event.wait()
        return result_holder[0] if result_holder[0] is not None else False

    # ---- bindings ---------------------------------------------------------

    def action_clear(self) -> None:
        history = self.query_one(MessageHistory)
        history.clear_history()
        self._history = []
        history.append_info("History cleared.")

    def action_toggle_raw(self) -> None:
        self._raw_output = not self._raw_output
        history = self.query_one(MessageHistory)
        history.append_info(f"Raw output: {'on' if self._raw_output else 'off'}")

    # ---- main loop reference (set by Textual at run time) -----------------

    @property
    def _main_loop(self) -> Any:
        # Textual stores the asyncio loop on the app as `_loop` in
        # some versions and on the runner in others. We try a few
        # known accessors.
        loop = getattr(self, "_loop", None)
        if loop is not None:
            return loop
        # Fallback: the current running loop. This works inside
        # @work(thread=True) workers because Textual installs the
        # main loop reference.
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            return asyncio.get_running_loop()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    LinuxTUIApp().run()


if __name__ == "__main__":
    main()
