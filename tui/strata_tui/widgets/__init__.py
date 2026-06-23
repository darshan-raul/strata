"""TUI widgets: the visual layer.

This package contains the three custom widgets the TUI uses
to display state:

- :class:`MessageHistory` — the scrollable log of conversation
  turns (user prompts, AI responses, tool calls, tool results).
- :class:`InputBox` — the single-line text widget where the
  user types their next prompt. (Defined in
  :mod:`strata_tui.widgets.input_box`.)
- :class:`StatusBar` — the one-line footer showing the model
  name and a "thinking..." indicator. (Defined in
  :mod:`strata_tui.widgets.status_bar`.)

All three are subclasses of Textual's built-in widgets. We
extend them only to add our domain-specific render methods
(``append_user``, ``append_ai``, ``append_tool_call``, etc.).

Why thin subclasses instead of raw Textual widgets?
--------------------------------------------------
The default Textual widgets give you ``write()`` and the
underlying ``Rich`` console; we want to give the App code a
small, opinionated API (one method per "thing the user sees
on screen") so the App doesn't have to know about Rich's
markup syntax.

The methods are also a natural place to put cross-cutting
concerns like "truncate long tool results" or "highlight
errors in red." The App code stays simple.
"""
