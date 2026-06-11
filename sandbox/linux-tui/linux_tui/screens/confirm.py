"""Confirmation modal for `run_command`.

Pops when the agent wants to execute a mutating command. The user
presses `y` to allow, `n` (or `Esc`) to deny. The result is
delivered back to the caller via a Textual `Dismiss` message.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

from linux_tui.tools.run_command import is_dangerous


class ConfirmScreen(ModalScreen[bool]):
    """A modal that asks the user to allow/deny a mutating command.

    Returns True if allowed, False if denied. Dismissed with
    `screen.dismiss(result)`.
    """

    BINDINGS = [
        Binding("y", "allow", "Allow", show=True),
        Binding("n", "deny", "Deny", show=True),
        Binding("escape", "deny", "Deny", show=False),
    ]

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 80%;
        max-width: 100;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #confirm-title {
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    #confirm-cmd {
        color: $text;
        background: $boost;
        padding: 0 1;
        margin-bottom: 1;
    }
    #confirm-warning {
        color: $error;
        margin-bottom: 1;
    }
    #confirm-help {
        color: $text-muted;
    }
    """

    def __init__(self, tool_name: str, args: dict) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._args = args

    def compose(self) -> ComposeResult:
        cmd = self._args.get("cmd", "(no cmd arg)")
        dangerous, reason = is_dangerous(cmd)

        with Vertical(id="confirm-dialog"):
            yield Label("⚠  Mutating tool requested", id="confirm-title")
            yield Label(f"Tool: [bold]{self._tool_name}[/]", id="confirm-tool")
            yield Label(cmd, id="confirm-cmd")
            if dangerous:
                yield Label(f"⚠  {reason}", id="confirm-warning")
            yield Label(
                "Press [bold]y[/] to allow, [bold]n[/] (or [bold]Esc[/]) to deny.",
                id="confirm-help",
            )

    def action_allow(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)


def make_confirm_text(tool_name: str, args: dict) -> Text:
    """Helper for non-modal contexts: build a Rich Text prompt."""
    cmd = args.get("cmd", "(no cmd arg)")
    dangerous, reason = is_dangerous(cmd)
    t = Text()
    t.append("⚠  Mutating tool requested\n", style="bold yellow")
    t.append(f"Tool: {tool_name}\n")
    t.append(f"Cmd:  {cmd}\n")
    if dangerous:
        t.append(f"⚠  {reason}\n", style="bold red")
    t.append("Press y to allow, n to deny.\n", style="dim")
    return t
