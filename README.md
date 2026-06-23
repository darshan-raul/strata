# Strata

A two-tier system for managing **existing** Kubernetes clusters conversationally
and via kubectl-style commands.

- **TUI** — A Python + Textual terminal app that runs on your laptop. BYOK
  (Bring Your Own Key) for the LLM. k9s-style command palette (`:get`,
  `:describe`, `:logs`, `:apply`, `:delete`) plus a chat rail to a
  LangGraph agent.
- **Backend** — A remote Kubernetes cluster (EKS) the maintainer operates.
  Multi-tenant. Runs MCP servers, RAG, the agent, the web dashboard,
  and stores per-user encrypted cluster credentials.

The TUI is the only mutating surface and the only one that can chat.
The web dashboard is a read-only viewer plus signup/login (the
account system of record). All long-lived credentials live in the
backend, encrypted at rest.

The default model is **MiniMax M3** (OpenAI-compatible) used directly
by the TUI for BYOK and through LiteLLM on the backend. Swappable to
Bedrock / Anthropic / OpenAI without code changes.

For the full plan, locked decisions, and phase roadmap, see
[AGENTS.md](AGENTS.md). For live state across sessions, see
[handoff.md](handoff.md). For the docs library, see
[docs/](docs/).

## Status

**Phase 0 — Reset + TUI graduation.** The TUI smoke test passes;
the backend doesn't exist yet.

```bash
cd tui && uv sync && uv run strata
```

## License

TBD.
