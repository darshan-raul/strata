"""Input box — single-line. Enter submits.

Subclasses Textual's `Input` (the single-line text widget) rather
than `TextArea` (multi-line). The single-line widget is the right
shape for a chat REPL prompt: hit Enter, the message is sent.
`TextArea` was overkill and its `Submit` message doesn't exist in
Textual 8.2.x.
"""
from __future__ import annotations

from textual.widgets import Input


class InputBox(Input):
    """The user prompt area. Enter submits; the standard Input behavior."""
    pass
