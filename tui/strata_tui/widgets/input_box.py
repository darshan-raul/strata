"""Input box — single-line. Enter submits.

This module is intentionally tiny. The whole point is that
Textual's built-in ``Input`` widget is exactly what we want
for a chat REPL: a single-line text field, Enter posts a
``Submitted`` message, that's it. We subclass ``Input`` (as
``InputBox``) only to give it a project-specific name and to
document the intent.

Why a subclass at all?
----------------------
Three reasons:

1. **Semantic naming.** The TUI App code says
   ``self.query_one(InputBox)``. That name signals "this is
   the prompt area" without needing a comment. A bare
   ``query_one(Input)`` would be ambiguous.

2. **Type hinting.** The App's type hints reference
   ``InputBox``, which makes the intent clear to readers and
   helps mypy catch confusion with other Input widgets (we
   only have one, but the type story is cleaner).

3. **Future extension.** When we add features like "history
   recall with up arrow" or "command completion," they'll
   live here as overrides of ``Input`` methods.

What about ``TextArea`` (the multi-line widget)?
------------------------------------------------
We considered it for "paste a long log line" use cases but
rejected it. ``TextArea`` requires the user to press a
modifier (Ctrl+Enter) to insert a newline, which is a worse
REPL UX than "Enter submits, Shift+Enter inserts a newline."
And we already have a workaround: long tool output is
truncated, not pasted.

The ``Input`` widget's ``Submitted`` message
--------------------------------------------
When the user presses Enter in an ``Input``, Textual posts
an ``Input.Submitted`` message. The App's
``@on(_Input.Submitted)`` handler picks it up and starts the
agent turn. See :mod:`strata_tui.app` for the handler.

The text the user typed is in ``event.value``. The App
clears the field by setting ``input_box.value = ""``.

See https://textual.textualize.io/widgets/input/ for the full
``Input`` API.
"""
from __future__ import annotations

from textual.widgets import Input


class InputBox(Input):
    """The user prompt area. Enter submits; standard ``Input`` behavior.

    Inherits everything from Textual's ``Input``:
    ``value``, ``placeholder``, ``password``, ``disabled``,
    etc. The App sets ``placeholder`` at mount time to
    "Ask about the local Linux box..." and clears ``value``
    after each submit.
    """
    # Intentionally empty. Subclass exists for the type name
    # and as an extension point. Adding any method overrides
    # here would change the user-visible behavior of the
    # input; we don't have a reason to do that yet.
    pass
