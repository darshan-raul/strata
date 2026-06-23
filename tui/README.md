# Strata TUI

The Strata terminal user interface. Python 3.12, Textual,
LangChain, LangGraph, MiniMax M3 (BYOK).

Phase 0 scope:

- Launches a Textual TUI.
- Reads MiniMax API key from `.env` and chats with MiniMax M3.
- Renders a placeholder for `:get` commands ("backend comes in
  Phase 1").
- Pytest suite verifies the chat surface.

Future phases (per `../AGENTS.md`):

- **Phase 1:** LangGraph agent + MCP-backed k8s tools. End-to-end
  `tui :get pods` flow against a local kind-hosted backend.
- **Phase 2:** OIDC device-code login.
- **Phase 3:** Mutation tools + confirmation modal.
- **Phase 4+:** Cluster context switcher, encrypted credentials.

## Install

```bash
cd tui
uv sync
cp .env.example .env   # then edit, set MINIMAX_API_KEY
```

## Run

```bash
uv run strata           # launches the Textual TUI
```

Or directly:

```bash
uv run python -m strata_tui
```

## Test

```bash
uv run pytest
```

Tests use `FakeListChatModel` from `langchain-core` — no real LLM
network call is made.

## Layout

```
tui/
├── pyproject.toml
├── .env.example
├── strata_tui/
│   ├── __init__.py
│   ├── __main__.py     # python -m strata_tui entry point
│   ├── app.py          # the Textual App
│   ├── config.py       # settings loader (.env + env vars)
│   ├── agent/          # LangChain + LangGraph (Phase 1+)
│   ├── api/            # backend HTTP client (Phase 1+)
│   ├── commands/       # kubectl-style :commands (Phase 1+)
│   ├── screens/        # modal screens (Phase 3+)
│   ├── tools/          # placeholder echo tool (Phase 0)
│   └── widgets/        # MessageHistory, StatusBar, etc.
└── tests/              # pytest suite
```

## See also

- `../AGENTS.md` — full plan and locked decisions
- `../handoff.md` — live state
- `../docs/textual.md` — Textual reference
- `../docs/strata/tui-architecture.md` — TUI internal design