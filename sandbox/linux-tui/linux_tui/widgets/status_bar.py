"""Status bar — shows model name, current tool count, etc."""
from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """A single-line status bar at the bottom of the TUI."""

    def __init__(self, model_name: str) -> None:
        super().__init__(f"model: {model_name} | Ctrl+C quit | Ctrl+L clear | Ctrl+R raw/parsed")
        self._model_name = model_name

    def set_model(self, model_name: str) -> None:
        self._model_name = model_name
        self.update(f"model: {model_name} | Ctrl+C quit | Ctrl+L clear | Ctrl+R raw/parsed")

    def set_busy(self, busy: bool) -> None:
        suffix = "thinking..." if busy else "ready"
        self.update(f"model: {self._model_name} | {suffix} | Ctrl+C quit | Ctrl+L clear | Ctrl+R raw/parsed")
