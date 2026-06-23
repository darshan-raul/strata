# Strata docs

Reference documentation for the technologies Strata is built on
and the project's own architecture. Read these in order if you're
new to the project; jump to a specific doc if you know what you
need.

---

## Learning order

If you're new to the agentic-AI stack, read in this order:

1. **[langchain.md](./langchain.md)** + the
   **[langchain/](./langchain/)** deep-dive — chat models,
   messages, tools, the `Runnable` protocol, output parsers,
   runnables, streaming, caching, tracing, testing. The base
   layer.
2. **[langgraph.md](./langgraph.md)** + the
   **[langgraph/](./langgraph/)** deep-dive — state machines on
   top of LangChain. `StateGraph`, `ToolNode`,
   `tools_condition`, `Command`, checkpointers, `interrupt()`,
   subgraphs, HITL, streaming, memory stores. The orchestration
   layer.
3. **[mcp.md](./mcp.md)** + the **[mcp/](./mcp/)** deep-dive —
   the wire protocol between the agent and the cluster-facing
   servers. FastMCP 3.x, transports, the four primitives.
4. **[textual.md](./textual.md)** — the TUI framework Strata
   uses for the local interface. `App`, `Widget`, `ModalScreen`,
   workers, `call_from_thread`.
5. **[kubernetes.md](./kubernetes.md)** — how Strata talks to
   user clusters. The Python `kubernetes` client, RBAC patterns,
   the kubeconfig shape we extract.
6. **[keycloak.md](./keycloak.md)** — the OIDC provider in the
   backend. Realm config, device-code flow, JWT validation.
7. **[envoy-gateway.md](./envoy-gateway.md)** — the ingress.
   Gateway API, ext-authz for Keycloak JWT, rate limiting.
8. **[cnpg.md](./cnpg.md)** — CloudNativePG, the in-cluster
   Postgres operator.
9. **[external-secrets.md](./external-secrets.md)** — ESO +
   AWS Secrets Manager for long-lived secrets.
10. **[litellm.md](./litellm.md)** — the OpenAI-compatible
    proxy that sits between the backend agent and the actual
    LLM providers. The model layer.
11. **[bedrock.md](./bedrock.md)** — what's behind LiteLLM in
    the backend's default config. Nova Pro, Titan v2, SigV4 auth.
    The provider layer.
12. **[rag.md](./rag.md)** — retrieval-augmented generation, the
    retriever-service, Qdrant, the `retrieve` node. The context
    layer.
13. **[nextjs.md](./nextjs.md)** — the web dashboard. App
    Router, server components, server actions, streaming tokens,
    auth, forms. The presentation layer.

Then read the project-specific docs:

14. **[strata/tui-architecture.md](./strata/tui-architecture.md)**
15. **[strata/backend-architecture.md](./strata/backend-architecture.md)**
16. **[strata/mcp-architecture.md](./strata/mcp-architecture.md)**
17. **[strata/security-model.md](./strata/security-model.md)**
18. **[strata/data-flow.md](./strata/data-flow.md)**

---

## Companion documents (not in `docs/`)

- **[AGENTS.md](../AGENTS.md)** — the source of truth for the
  plan, locked decisions, and phase status. Read first in any
  new session.
- **[handoff.md](../handoff.md)** — live state across sessions.
  Read second.
- **[README.md](../README.md)** — human-facing project overview.

---

## Doc conventions

- All docs are written assuming you're a senior k8s engineer
  who knows nothing about LangChain, LangGraph, RAG, or
  FastMCP. (That's the original author; if you're past that,
  the early sections may feel slow.)
- Code examples are project-shaped (Strata's actual files, not
  toy examples).
- "Phase 1", "Phase 5", etc. refer to phases in
  [AGENTS.md §5](../AGENTS.md#5-build-phases).
- The word "**carrier**" refers to the backend k8s
  infrastructure (and the user's clusters). The word
  "**product**" refers to the agentic-AI work.
- Tech-reference docs (langchain/, langgraph/) are written
  against the latest edge of LangChain / LangGraph (1.0+ /
  0.3+), with older concepts (e.g. `langchain_community`,
  `AgentExecutor`, `ConversationBufferMemory`) called out as
  "legacy / migration notes" so you're not surprised when you
  encounter them in older tutorials.