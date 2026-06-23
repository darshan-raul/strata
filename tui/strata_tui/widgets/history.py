"""Message history widget — a scrollable log of conversation turns.

Renders each message with a role tag and a body. Tool calls
and results are rendered as compact "called X / got Y"
blocks. The final AI message is rendered as a "Strata:"
block.

What this widget does
---------------------
``MessageHistory`` is a thin subclass of Textual's
``RichLog``. ``RichLog`` is a scrollable, auto-wrapping text
area that's optimized for streaming writes. We extend it
with domain-specific methods (``append_user``,
``append_ai``, ``append_tool_call``, etc.) so the App
doesn't have to know about Rich's markup syntax.

The "shrink" parameter
----------------------
Some of the append methods take ``shrink=False`` when
writing chunks of a streamed AI response. This tells
``RichLog`` not to "shrink" the entry to fit — i.e. not to
collapse multiple consecutive writes into one line. We want
the streamed tokens to appear on the same line as the
"Strata:" prefix; without ``shrink=False`` the log might
re-render and lose the visual continuity.

(In the current code, the App doesn't actually stream
token-by-token; it writes the full AI response at once
after the turn completes. The ``shrink``-related methods
are kept here for the future token-streaming feature.)

Truncation
----------
``append_tool_result`` truncates long results to 800 chars
for the on-screen display. The full result is still in the
message history (which the App stores and passes back to
the model on the next call); the truncation is purely a
display concern so the TUI doesn't get spammed with megabytes
of grep output.

The ``render_message`` helper
-----------------------------
The standalone ``render_message`` function at the bottom is
a debug aid: it formats a single LangChain message as a
short string like ``"[A] hello (tool_calls: list_clusters)"``.
Not used by the App at runtime; useful in a REPL or for
debugging.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from textual.widgets import RichLog


class MessageHistory(RichLog):
    """A scrollable log of conversation messages.

    Each ``append_*`` method writes one line (or one block) of
    Rich-formatted text to the log. Textual's ``RichLog``
    auto-wraps long lines and provides scrolling. We just
    delegate to ``self.write``.
    """

    def append_user(self, text: str) -> None:
        """Write a user prompt line.

        Format: ``You: {text}`` in bold cyan. The ``[bold cyan]``
        markup is Rich syntax — Textual's ``RichLog`` consumes
        it via the ``rich`` library under the hood.
        """
        self.write(f"[bold cyan]You:[/] {text}")

    def append_ai(self, text: str) -> None:
        """Write the final AI response.

        Format: ``Strata: {text}`` in bold green. Empty text
        (e.g. a pure tool-call response) is skipped — the
        user doesn't need to see "Strata: ".
        """
        if text:
            self.write(f"[bold green]Strata:[/] {text}")

    def append_ai_stream_start(self) -> None:
        """Mark the start of a streamed AI response.

        Writes the "Strata: " prefix without a trailing
        newline. The streamed tokens follow in
        :meth:`append_ai_stream_chunk`. ``shrink=False``
        prevents ``RichLog`` from collapsing the prefix into
        a one-line entry.
        """
        self.write("[bold green]Strata:[/] ", shrink=False)

    def append_ai_stream_chunk(self, chunk: str) -> None:
        """Append one streamed token.

        Called once per token from the LLM. Empty chunks
        (which the model sometimes emits between sentences)
        are skipped.
        """
        if chunk:
            self.write(chunk, shrink=False)

    def append_ai_stream_end(self) -> None:
        """Mark the end of a streamed AI response.

        Writes an empty line so the next user prompt starts
        on a fresh visual line.
        """
        self.write("")  # newline

    def append_tool_call(self, name: str, args: dict) -> None:
        """Write a "→ tool_name({...})" line.

        Shown in dim gray to indicate it's a system-level
        event, not user/assistant content. ``json.dumps``
        formats the args dict; ``default=str`` makes
        non-JSON-serializable values (like Path) fall back to
        their string form.
        """
        # The ``import json`` is local to keep the module's
        # import surface small. ``json`` is only needed when
        # a tool call is appended, which is most invocations
        # but not all.
        import json
        args_repr = json.dumps(args, default=str) if args else ""
        self.write(f"  [dim]→ {name}({args_repr})[/]")

    def append_tool_result(self, name: str, content: str) -> None:
        """Write a "← tool_name: <preview>" block.

        Long results are truncated to 800 chars for display.
        The full result is still in the message history
        (managed by the App) and gets passed back to the
        model on the next call. The truncation is purely
        for the human's screen real estate.
        """
        # Truncate to 800 chars + ellipsis. 800 is enough
        # for a useful preview without flooding the screen;
        # the model still sees the full result.
        preview = content if len(content) <= 800 else content[:800] + "\n... (truncated for display)"
        # ``\\n`` after the label puts the preview on the
        # next line, indented. The ``\\n{preview}`` after
        # the closing ``[/]`` keeps the preview's
        # indentation relative to the label.
        self.write(f"  [dim yellow]← {name}:[/]\n{preview}")

    def append_error(self, text: str) -> None:
        """Write an error line in bold red.

        Used for fatal errors (e.g. missing API key, network
        failures) and for tool errors the loop couldn't
        recover from. Distinguishable from
        :meth:`append_tool_result` by the bold (vs. dim)
        styling.
        """
        self.write(f"[bold red]Error:[/] {text}")

    def append_info(self, text: str) -> None:
        """Write an informational line in dim text.

        Used for startup messages, mode-change notifications
        (raw output on/off), and other non-error
        out-of-band signals.
        """
        self.write(f"[dim]{text}[/]")

    def clear_history(self) -> None:
        """Clear all log content.

        Called when the user presses Ctrl+L. Note: this
        clears the *display*, not the App's internal message
        list. The App's :meth:`action_clear` does both.
        """
        self.clear()


def render_message(msg) -> str:
    """Format a single langchain message for display (debug aid).

    Not used by the App at runtime; useful in a Python REPL
    for inspecting a message list::

        >>> from strata_tui.widgets.history import render_message
        >>> from langchain_core.messages import HumanMessage
        >>> render_message(HumanMessage(content="hi"))
        '[H] hi'

    The format is ``[<role>] <content>`` with tool calls and
    tool status appended.
    """
    if isinstance(msg, HumanMessage):
        return f"[H] {msg.content}"
    if isinstance(msg, AIMessage):
        # If the message has tool calls, append a short
        # summary so you can see at a glance which tools the
        # model wanted to call.
        tcs = ", ".join(tc.get("name", "?") for tc in (msg.tool_calls or []))
        suffix = f" (tool_calls: {tcs})" if tcs else ""
        return f"[A] {msg.content}{suffix}"
    if isinstance(msg, ToolMessage):
        # ``status`` is "success" by default; tool errors set
        # it to "error" (see the agent loop).
        status = getattr(msg, "status", "success")
        return f"[T/{status}] {msg.content}"
    return f"[?] {msg}"
