# Strata backend

> **Stub for Phase 0.** The backend lands in Phase 1.

The remote Kubernetes cluster (managed by the maintainer) that
runs Strata's multi-tenant services.

Planned layout:

```
backend/
├── helm/strata/         # umbrella Helm chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/       # one Deployment per service + ingress
├── services/            # source for each service
│   ├── shared/          # Go module: db, http, auth, crypto, mcp, litellm
│   ├── orchestrator/    # Go (chi, sqlx) — REST API + auth
│   ├── retriever/       # Go — RAG
│   ├── rag-indexer/     # Go — ingestion
│   └── agent-service/   # Python (FastAPI + LangGraph)
├── mcp-servers/         # FastMCP servers (Python)
│   ├── k8s/
│   ├── argocd/
│   ├── aws/
│   ├── helm/
│   └── shared/
└── tests/               # integration tests
```

## Services

- **orchestrator (Go)** — REST API, JWT validation, RBAC,
  cluster-credential encryption, cluster registry.
- **retriever (Go)** — `/retrieve` and `/index` over Qdrant
  + LiteLLM (embeddings).
- **rag-indexer (Go)** — every 60s, read Postgres + uploaded
  docs and re-index.
- **agent-service (Python)** — LangGraph agent, talks to MCP
  servers over streamable HTTP, streams responses as NDJSON.
- **litellm (Python)** — OpenAI-compatible proxy to the hosted
  LLM provider (Bedrock default).
- **mcp-servers (Python)** — FastMCP servers: k8s, argocd, aws,
  helm. One Deployment per server.

## Phase 1 plan

End-to-end smoke test:

```bash
make backend-up   # create kind cluster, helm install strata
make tui-dev      # in another shell
# in TUI:
#   :get pods
#   should return pods from a mock cluster the orchestrator knows
```

## See also

- `../AGENTS.md` — full plan
- `../docs/strata/backend-architecture.md` — design doc