"""Message history widget — a scrollable log of conversation turns.

Renders each message with a role tag and a body. Tool calls and
results are rendered as a compact "called X / got Y" block. The
final AI message is rendered as a "Strata:" block.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from textual.widgets import RichLog


class MessageHistory(RichLog):
    """A scrollable log of conversation messages."""

    def append_user(self, text: str) -> None:
        self.write(f"[bold cyan]You:[/] {text}")

    def append_ai(self, text: str) -> None:
        if text:
            self.write(f"[bold green]Strata:[/] {text}")

    def append_ai_stream_start(self) -> None:
        """Mark the start of a streamed AI response."""
        self.write("[bold green]Strata:[/] ", shrink=False)

    def append_ai_stream_chunk(self, chunk: str) -> None:
        """Append a streamed token."""
        if chunk:
            self.write(chunk, shrink=False)

    def append_ai_stream_end(self) -> None:
        """Mark the end of a streamed AI response."""
        self.write("")  # newline

    def append_tool_call(self, name: str, args: dict) -> None:
        import json
        args_repr = json.dumps(args, default=str) if args else ""
        self.write(f"  [dim]→ {name}({args_repr})[/]")

    def append_tool_result(self, name: str, content: str) -> None:
        # Truncate very long results in the on-screen log; the full
        # content is still in the message history (for the next LLM call).
        preview = content if len(content) <= 800 else content[:800] + "\n... (truncated for display)"
        self.write(f"  [dim yellow]← {name}:[/]\n{preview}")

    def append_error(self, text: str) -> None:
        self.write(f"[bold red]Error:[/] {text}")

    def append_info(self, text: str) -> None:
        self.write(f"[dim]{text}[/]")

    def clear_history(self) -> None:
        self.clear()


def render_message(msg) -> str:
    """Format a single langchain message for display (debug aid)."""
    if isinstance(msg, HumanMessage):
        return f"[H] {msg.content}"
    if isinstance(msg, AIMessage):
        tcs = ", ".join(tc.get("name", "?") for tc in (msg.tool_calls or []))
        suffix = f" (tool_calls: {tcs})" if tcs else ""
        return f"[A] {msg.content}{suffix}"
    if isinstance(msg, ToolMessage):
        status = getattr(msg, "status", "success")
        return f"[T/{status}] {msg.content}"
    return f"[?] {msg}"
