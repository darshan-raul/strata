# Strata TUI architecture

> **Stub for Phase 0.** Full doc lands in Phase 1.

Internal design of the Strata TUI. Audience: anyone modifying
`tui/strata_tui/`.

Outline:

1. The `StrataTUIApp` class — top-level layout, bindings
2. The agent loop — LangChain in Phase 0, LangGraph in Phase 1
3. The widget layer (history, input, status, resource table)
4. The command palette (`:get`, `:describe`, etc.)
5. The api client (`strata_tui/api/client.py`)
6. Auth flow (OIDC device-code)
7. Configuration (`~/.config/strata/`)
8. Testing strategy (Textual `App.run_test`)
9. What to read next