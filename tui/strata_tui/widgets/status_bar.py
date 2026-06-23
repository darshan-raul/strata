"""Status bar — shows model name + busy state.

A one-line footer at the bottom of the TUI. Two pieces of
information:

- **Model name.** Which model is wired up (e.g.
  ``MiniMax-M3``). The user can sanity-check that the
  config is right at a glance.
- **Busy state.** Either ``ready`` or ``thinking...``.
  Flips to ``thinking...`` while the agent turn is running
  and back to ``ready`` when it finishes.

Plus a static legend of the keybindings (Ctrl+C quit, etc.)
so the user doesn't have to remember them.

Why a single line?
------------------
The status bar is meant to be glanceable, not informative.
Detailed information (token counts, tool history) belongs
in the message history, not the status bar.

Why ``Static`` (the Textual widget)?
-------------------------------------
``Static`` is Textual's "I want to display a string" widget.
It doesn't handle input, doesn't manage focus, doesn't have
a value attribute. We just call ``.update(text)`` to change
the displayed content.

For a more complex status (e.g. a progress bar, a per-tool
spinner), we'd reach for ``ProgressBar`` or a custom
``Widget``. For now, ``Static`` is the right shape.
"""
from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """A single-line status bar at the bottom of the TUI.

    The displayed text is built from three parts: model name,
    busy state, and a static keybinding legend. The
    keybinding legend is hard-coded; the other two are
    updated via :meth:`set_model` and :meth:`set_busy`.
    """

    def __init__(self, model_name: str = "strata", **kwargs) -> None:
        """Initialize the bar with the model name.

        The busy state defaults to ``ready``. The keybinding
        legend is built once and reused across updates.
        ``model_name`` is optional so the App can construct
        the bar before it knows the model, then call
        :meth:`set_model` once it has read the config.
        Additional ``**kwargs`` are forwarded to ``Static`` so
        the App can set ``id`` / ``classes`` at compose time.
        """
        # Stash the model name on the instance so the
        # render method and the ``set_model`` / ``set_busy``
        # updates don't have to thread it through every call.
        self._model_name = model_name
        # The ``super().__init__()`` call takes the initial
        # text. We build it inline via ``_render_text`` so
        # ``set_model`` and ``set_busy`` can reuse the same
        # formatting.
        super().__init__(self._render_text(busy=False), **kwargs)

    def set_model(self, model_name: str) -> None:
        """Update the displayed model name.

        Called when the App detects a config change (e.g.
        user sets a different ``MINIMAX_MODEL`` env var and
        restarts). For now, this is a no-op in practice
        because the model is read once at App start; the
        method exists for completeness.
        """
        self._model_name = model_name
        # ``update`` is a ``Static`` method that replaces the
        # rendered content.
        self.update(self._render_text(busy=False))

    def set_busy(self, busy: bool) -> None:
        """Flip the busy state between ``ready`` and ``thinking...``.

        Called by the App:

        - ``set_busy(True)`` when an agent turn starts (the
          model is being invoked).
        - ``set_busy(False)`` when the turn finishes (success
          or failure).

        The TUI doesn't show a spinner — ``thinking...`` is
        enough indication for a chat-style REPL.
        """
        self.update(self._render_text(busy=busy))

    def _render_text(self, *, busy: bool) -> str:
        """Build the status bar text.

        Reads the model name from ``self._model_name`` and
        combines it with the busy flag and the static
        keybinding legend.

        Why the rename from ``_render``? Textual's
        :class:`~textual.widget.Widget` defines an internal
        ``_render`` method that's part of the render
        pipeline. Our earlier staticmethod named ``_render``
        shadowed the base — Textual's render loop would call
        ``self._render()`` with no arguments, hit our
        ``model_name`` parameter, and crash. Renaming to
        ``_render_text`` keeps the helper out of the way.

        Args:
            busy: Whether the agent is currently running.

        Returns:
            A single-line string with model name, busy state,
            and keybinding legend, joined with ``|``.
        """
        # The ``|`` separator is the standard "legend cell"
        # delimiter in TUIs. It scans well in monospace.
        suffix = "thinking..." if busy else "ready"
        return f"model: {self._model_name} | {suffix} | Ctrl+C quit | Ctrl+L clear | Ctrl+R raw/parsed"
