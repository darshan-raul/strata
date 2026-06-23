"""Entry point: ``python -m strata_tui``.

This is the smallest possible Python entry point: import the App
class, instantiate it, and call ``.run()``. The interesting code
is in :mod:`strata_tui.app`; this module just plugs the package
into Python's ``-m`` convention so users can type
``python -m strata_tui`` from any directory (as long as the venv
is activated).

Why a module-level ``main()`` and an ``if __name__ == "__main__"``
guard? The guard is the standard idiom for "only run this when
the file is the entry point, not when it's imported." A future
test could ``from strata_tui.__main__ import main`` without
auto-launching a TUI.
"""
from strata_tui.app import StrataTUIApp


def main() -> None:
    """Build the App and hand control to Textual's event loop.

    ``App.run()`` blocks until the user quits (Ctrl+C). It returns
    ``None`` and the process exits normally.
    """
    # Construct the App object (does NOT start the UI yet — just
    # sets up instance state via ``__init__``).
    app = StrataTUIApp()
    # Hand control to Textual. This call blocks until the user
    # exits the TUI. ``App.run()`` internally does the asyncio
    # event loop setup, terminal raw mode, input parsing, etc.
    app.run()


# Standard Python entry-point guard. Without this, just importing
# ``strata_tui.__main__`` (e.g. from a test) would launch a TUI.
if __name__ == "__main__":
    main()
