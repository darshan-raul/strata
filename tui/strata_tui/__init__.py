"""strata-tui: the Strata terminal user interface.

The primary hands-on surface of Strata. A Textual TUI that runs
on the user's local laptop and talks to a Strata backend over
HTTPS with a per-user JWT.

What the package is
-------------------
A terminal user interface built with
`Textual <https://textual.textualize.io/>`_ that combines:

- A **k9s-style command palette** for direct cluster operations
  (``:get``, ``:describe``, ``:logs``, ``:apply``, ``:delete``).
  Direct mutations are gated by a confirmation modal.
- An **agent chat rail** that talks to the backend's LangGraph
  agent. The agent in turn calls MCP servers over streamable HTTP
  to inspect and act on the user's registered Kubernetes clusters.

The TUI uses **MiniMax M3** (OpenAI-compatible) directly via
``langchain-openai`` for the BYOK LLM path. It does not require
the backend for LLM calls; it only requires the backend for
cluster data + MCP.

Layout
------
    strata_tui/
        __main__.py        # python -m strata_tui entry point
        app.py             # the Textual App class (top of the runtime stack)
        agent/             # LangChain + LangGraph agent loop (Phase 1+)
        api/               # HTTP client to the backend orchestrator
        commands/          # kubectl-style :command implementations
        screens/           # Textual modal screens (confirmation, login, ctx)
        widgets/           # Textual widgets (history, resource table, status bar)
        config.py          # ~/.config/strata/ paths and config loading

Entry points
------------
* ``python -m strata_tui``  — runs the TUI.
* ``uv run strata_tui``     — same, via the ``pyproject.toml`` script.

See :mod:`strata_tui.__main__` for the implementation.
"""
__version__ = "0.1.0"