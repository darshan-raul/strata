# Strata v2

> **Read this first.** Source of truth for what Strata is, how it's organized, and the build plan every agent follows. `handoff.md` tracks live state across sessions.

---

## 1. What Strata v2 is

A two-tier system for managing **existing** Kubernetes clusters conversationally + via kubectl-style commands.

- **TUI** (local laptop, Python + Textual, BYOK LLM key) — the user's hands-on surface. k9s-style command palette plus an agent chat rail. Default model: MiniMax M3.
- **Backend** (a remote k8s cluster the author manages, multi-tenant, OIDC) — runs MCP servers, RAG, the LangGraph agent, the web dashboard, and stores per-user encrypted cluster credentials.

The TUI never talks to k8s directly. It authenticates to the backend with a JWT, sends commands, and streams chat responses. The backend's LangGraph agent calls MCP servers over HTTP/SSE; the MCP servers use the user's stored kubeconfig to talk to the user's clusters. End-to-end request paths go: **TUI → Envoy Gateway → orchestrator / agent-service / web → MCP servers → user's k8s clusters**.

The first version is single-author / dev-grade. Multi-tenancy is wired in from day one (per-user JWT, per-user encryption DEK, per-user Qdrant collections) but the operations story (HA, backups, observability) lands later.

---

## 2. Locked decisions (do not re-litigate)

### Product shape

| Concern | Choice | Why |
|---|---|---|
| **Two-tier architecture** | TUI (local laptop) + Backend (remote k8s cluster) | Matches "TUI to manage existing k8s clusters + a web dashboard for signup/login". |
| **TUI scope** | k9s-style commands (`:get`, `:describe`, `:logs`, `:apply`, `:delete`) + agent chat rail | Both surfaces in one app; mutations gated by confirmation modal mirroring `sandbox/linux-tui/screens/confirm.py`. |
| **Primary interface** | TUI | Web dashboard is read-only; TUI is the only mutating surface and the only one that can chat. |
| **Web dashboard scope** | Read-only viewer + signup/login (no web chat) | Auth is the web's job; data is the TUI's job. |
| **TUI LLM auth** | BYOK (env var / OS keyring); default MiniMax M3 | No backend roundtrip for the LLM call when the user has the key locally. |
| **Backend LLM auth** | Hosted key via LiteLLM proxy; default MiniMax M3; easily swappable | Centralized credential mgmt + cross-cutting features (retries, fallbacks, virtual keys). |
| **k8s cluster credentials** | Stored encrypted in backend (AES-GCM, KMS-wrapped DEK); TUI never sees raw kubeconfig | Per-user isolation; revocable from backend. |
| **MCP transport** | All MCP servers run in backend k8s cluster; HTTP/SSE (streamable-HTTP) transport | Single security boundary; one auth story; easier to scale. |
| **RAG** | Qdrant in backend, per-user collections, rag-indexer ingests per-user cluster state + uploaded docs | Per-user isolation, per-user RAG collections, retrieval goes through `retriever-service` only. |
| **Auth** | Keycloak (OIDC); TUI uses device-code flow via the web dashboard; web uses standard auth-code | Keycloak over Zitadel: wider deployment, better Helm chart, OIDC support is mature. |
| **Ingress** | **Envoy Gateway** + cloud LoadBalancer; no Kong, no nginx-ingress | Native Gateway API, native ext-authz for Keycloak JWT validation, native rate limiting. |
| **Auth at the gateway** | Envoy Gateway ext-authz / OIDC integration via Envoy filter, OR oauth2-proxy sidecar in front of services | One consistent JWT validation point; backend services trust upstream identity. |
| **Backend Postgres** | CloudNativePG (in-cluster operator) | Backup/PITR/failover via operator; no RDS. |
| **Secrets** | External Secrets Operator → AWS Secrets Manager | GitOps-friendly, KMS-backed. |
| **Observability (deferred to Phase 9+)** | Prometheus + Grafana + Loki + Tempo (PLG), in-cluster | Standard OSS stack. |
| **Doc ownership** | AI-authored reference docs under `docs/`, user-reviewed and edited | Same as v1. |
| **TUI runtime** | Local laptop only; no in-cluster web-terminal variant | Native Textual feel; no browser-based TUI shim. |

### Tech / stack

| Concern | Choice |
|---|---|
| TUI | Python 3.12, [Textual](https://textual.textualize.io/), `uv` |
| TUI LLM client | `langchain-openai` pointed at MiniMax M3 (OpenAI-compatible) for BYOK path |
| TUI agent loop | LangChain `@tool` + LangGraph `StateGraph` with `ToolNode` (when tool calls come from MCP servers, the agent invokes them through a streamable-HTTP MCP client) |
| TUI command palette | Custom Textual command/screen layer; commands call backend REST endpoints |
| Backend services (Go) | Go 1.22+, `chi`, `sqlx`, `zerolog`, `pgx`, `client-go`, `kubernetes` Python client |
| Backend services (Python) | Python 3.12, FastAPI, LangChain 1.0+, LangGraph 0.3+, FastMCP 3.x |
| Backend LLM proxy | LiteLLM (OpenAI-compatible), pointing at MiniMax M3 default |
| Backend MCP servers | FastMCP 3.x, streamable-HTTP transport, one Deployment per server |
| Web | Next.js 15 (App Router), TypeScript, `pnpm` |
| Charts | Helm umbrella at `backend/helm/strata/` |
| Infra | Terraform in `infra/bootstrap/` (VPC, EKS, S3 TF state, KMS, ACM, IRSA) |
| CI | GitHub Actions, one workflow per tier |

---

## 3. Repo layout (target — Phase 0 in progress)

```
strata/
├── AGENTS.md                       # this file
├── handoff.md                      # live cross-session state
├── README.md                       # human-facing project overview
├── Makefile                        # top-level dev workflow
├── tui/                            # TEXTUAL TUI — primary interface
│   ├── pyproject.toml
│   ├── README.md
│   ├── strata_tui/                 # graduated from sandbox/linux-tui
│   └── tests/
├── backend/                        # REMOTE K8S CLUSTER (multi-tenant)
│   ├── helm/strata/                # umbrella Helm chart
│   ├── services/
│   │   ├── shared/                 # Go module: db, http, auth, crypto, mcp, litellm
│   │   ├── orchestrator/           # Go (chi, sqlx) — REST API + auth
│   │   ├── retriever/              # Go — RAG
│   │   ├── rag-indexer/            # Go — ingestion
│   │   └── agent-service/          # Python (FastAPI + LangGraph)
│   ├── mcp-servers/                # FastMCP servers (Python)
│   │   ├── k8s/
│   │   ├── argocd/
│   │   ├── aws/
│   │   ├── helm/
│   │   └── shared/
│   └── tests/
├── web/                            # NEXT.JS — signup/login + read-only dashboard
│   ├── package.json
│   └── app/
├── infra/                          # TERRAFORM — bootstrap the backend cluster
│   ├── bootstrap/
│   └── modules/
├── docs/                           # reference + project docs
│   ├── README.md
│   ├── langchain.md
│   ├── langchain/                  # 8 deep-dive files (ported from notes/)
│   ├── langgraph.md
│   ├── langgraph/                  # 12 deep-dive files (ported from notes/)
│   ├── litellm.md
│   ├── bedrock.md
│   ├── rag.md                      # rewritten for per-user
│   ├── mcp.md                      # NEW
│   ├── mcp/                        # NEW deep-dive
│   ├── textual.md                  # NEW
│   ├── kubernetes.md               # NEW
│   ├── nextjs.md                   # adapted (signup/login + dashboard)
│   ├── keycloak.md                 # NEW
│   ├── envoy-gateway.md            # NEW
│   ├── cnpg.md                     # NEW
│   ├── external-secrets.md         # NEW
│   └── strata/
│       ├── tui-architecture.md     # NEW
│       ├── backend-architecture.md # NEW
│       ├── mcp-architecture.md     # NEW
│       ├── security-model.md       # NEW
│       └── data-flow.md            # NEW
├── .github/workflows/              # CI per tier
└── notes/                          # personal scratchpad (kept; gitignored)
```

---

## 4. Architecture diagram (target end-state)

```
        ┌─────────────────────────┐
        │  Local laptop           │
        │  ┌───────────────────┐  │
        │  │  Strata TUI       │  │   ← Textual, BYOK LLM key
        │  │  (Python, uv)     │  │      JWT to backend
        │  └─────────┬─────────┘  │
        └────────────┼────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend k8s cluster (EKS, you manage)                      │
│                                                              │
│  AWS NLB → Envoy Gateway (Gateway API)                      │
│    │                                                          │
│    ├─▶ web (Next.js)         signup / login / device-code    │
│    ├─▶ orchestrator (Go)     REST API, JWT, RBAC, crypto     │
│    ├─▶ agent-service (Py)    LangGraph + LangChain           │
│    │     │                                                  │
│    │     │ streamable-HTTP                                   │
│    │     ▼                                                  │
│    ├─▶ mcp-servers (FastMCP)                                │
│    │     ├─ k8s       (per-user SA token)                   │
│    │     ├─ argocd                                          │
│    │     ├─ aws                                             │
│    │     └─ helm                                            │
│    ├─▶ retriever (Go)         /retrieve → Qdrant             │
│    ├─▶ rag-indexer (Go)       every 60s                      │
│    ├─▶ litellm (Py)           → Bedrock/OpenAI/Anthropic     │
│    ├─▶ postgres (CloudNativePG) users, clusters, creds       │
│    ├─▶ qdrant                per-user collections            │
│    ├─▶ keycloak              OIDC provider                   │
│    └─▶ external-secrets      → AWS Secrets Manager           │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Build phases

| # | Phase | Effort | What ships |
|---|---|---|---|
| 0 | **Reset + TUI graduation** | 1 evening | Delete stale (specs/, services/, cli/, sandbox/, onboarding/, old Makefile, old CI). Graduate `sandbox/linux-tui/` → `tui/strata_tui/`. Rewrite AGENTS.md, README.md, create handoff.md. Port `notes/langchain/`, `notes/langgraph/` → `docs/`. Stub out `docs/mcp/`, `docs/textual/`, `docs/keycloak/`, `docs/envoy-gateway/`, `docs/kubernetes/`. Smoke test: TUI launches, chats with MiniMax, shows a placeholder `:get` command. |
| 1 | **Backend skeleton on local kind** | 1 weekend | TUI talks to a kind-hosted backend: Go orchestrator with Postgres + JWT auth, FastMCP `k8s` server (read-only `:get` tools only), one end-to-end flow `tui :get pods → orchestrator → MCP server → python-kubernetes → result`. No web yet. No mutations yet. |
| 2 | **OIDC + signup/login** | 1 weekend | Keycloak in backend, Next.js web with signup/login, TUI gains `strata login` (OIDC device code). JWT propagation everywhere. |
| 3 | **Mutation tools + confirmation** | 1 weekend | MCP k8s server adds `delete`, `apply`, `exec` (all marked MUTATION). TUI confirmation modal mirrors `sandbox/linux-tui/screens/confirm.py`. LangGraph `interrupt()` for backend-side confirmation when called from agent chat. |
| 4 | **Encrypted cluster registry** | 1 weekend | Web dashboard "Add cluster" form. Backend stores kubeconfig encrypted at rest (AES-GCM with KMS-wrapped DEK). MCP server decrypts per request. TUI `:ctx list/use`. |
| 5 | **Web dashboard** | 1 weekend | Next.js dashboard: cluster list, per-cluster resource browser (read-only), history view of recent TUI/agent actions. |
| 6 | **RAG (per-user)** | 1 weekend | Qdrant in backend, rag-indexer ingests per-user cluster state + uploaded docs, retriever-service, agent's `retrieve` node, one conditional routing rule. |
| 7 | **More MCP servers** | 1 weekend | ArgoCD MCP, AWS MCP (read-only), Helm MCP. Demonstrate agent chaining. |
| 8 | **Real EKS bootstrap** | 1–2 weekends | `infra/bootstrap/` Terraform (VPC, EKS, S3, KMS, ACM, IRSA). Deploy the Helm chart to a real cluster. Promote from kind. |
| 9 | **Polish + CI** | ongoing | GitHub Actions per tier, e2e test (`tui :get pods` against mock MCP server in CI), docs polish, observability. |

**Order:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9.

---

## 6. Phase 0 — Reset + TUI graduation (current)

**Goal:** A clean v2 repo with a working TUI smoke test, ready for Phase 1 backend work.

### Delete

- `specs/strata_master_doc.md`, `specs/sample_app_architecture.md` (old Cognito/Flutter plan). `specs/archives/` stays (historical, per prior decision).
- `services/agent-service/` (empty skeleton, references deleted code).
- `cli/` (empty `.venv` + `__pycache__`).
- `sandbox/linux-tui/` (graduate; see below).
- `onboarding/` (empty; old CFN approach gone).
- `.github/workflows/go-services.yml`, `.github/workflows/node-service.yml` (reference deleted `sample-app/services/`).
- `Makefile` (old kind/litellm/agent targets).
- `strata-dev-kind.yaml` (replaced by per-tier configs).
- `sandbox/linux-tui/.env copy.example` (typo from recent commit).

### Keep / port

- `notes/langchain/01-mental-model.md` … `08-testing-and-pitfalls.md` → `docs/langchain/`.
- `notes/langgraph/01-mental-model.md` … `12-pitfalls.md` → `docs/langgraph/`.
- `notes/litellm.md`, `notes/bedrock.md` → `docs/`.
- `notes/rag.md` → `docs/rag.md` (rewrite for per-user).
- `notes/fastmcp-tutorial/mcp-curriculum/` content → `docs/mcp/` (deep-dive) and `backend/mcp-servers/` (code).
- `notes/strata/agent-architecture.md` → read for inspiration, then retire (architecture has changed).

### Graduate `sandbox/linux-tui/` → `tui/`

- Move `linux_tui/` package → `tui/strata_tui/`.
- Rename `linux_tui` package to `strata_tui`.
- Rename `pyproject.toml` project to `strata-tui`.
- Update imports in tests + WALKTHROUGH.
- Strip the "this is a sandbox, not part of Strata" disclaimers.
- Strip the "LangChain only, no LangGraph" constraints (we'll add LangGraph in Phase 1).
- Strip the "linux tools only" content (replace `system_info`, `disk_usage`, `grep`, `list_dir`, `read_file`, `run_command` later with k8s + MCP tools).

### Create

- New `AGENTS.md` (this file).
- New `README.md` (matches new scope).
- New `handoff.md` (live state).
- New `Makefile` (top-level: `make tui-dev`, `make backend-up`, `make logs-*`, `make reset`, `make test`).
- New `tui/` (graduated TUI).
- New `backend/` skeleton (empty dirs with `README.md` placeholders).
- New `web/` skeleton (empty dirs with `README.md` placeholders).
- New `infra/` skeleton (empty dirs with `README.md` placeholders).
- New `docs/` skeleton (stubs for mcp, textual, keycloak, envoy-gateway, kubernetes, cnpg, external-secrets, plus `docs/strata/` stubs).
- New `.github/workflows/` stubs: `tui.yml`, `backend.yml`, `web.yml`.
- New `.gitignore`.

### Verification

```bash
ls -la
# Should contain: AGENTS.md, README.md, handoff.md, Makefile, tui/, backend/, web/, infra/, docs/, .github/, .gitignore
# Should NOT contain: specs/, services/, cli/, sandbox/, onboarding/, strata-dev-kind.yaml

cd tui && uv sync && uv run strata    # TUI launches
# type "hello" — see a streamed response from MiniMax M3
# type ":get pods" — see a placeholder response ("not implemented yet, backend comes in Phase 1")
```

---

## 7. Cross-cutting rules

- **No nginx-ingress, no Kong.** Envoy Gateway only.
- **No Zitadel.** Keycloak only.
- **No vendor SDKs in the TUI's BYOK path beyond `langchain-openai`.** The user explicitly opted for OpenAI-compat (MiniMax) over LiteLLM for the TUI. The backend uses LiteLLM.
- **All cluster credentials live encrypted in the backend.** The TUI never sees raw kubeconfigs.
- **All MCP servers run in the backend.** None on the TUI.
- **All RAG retrieval goes through `retriever-service`.** `agent-service` and any other consumer call the retriever HTTP API, never Qdrant directly.
- **All long-lived secrets come from External Secrets Operator.** No `Secret` resources in Helm with literal values.
- **Cluster-to-cluster auth is OIDC + JWT.** No shared static API keys between Strata and customer clusters.
- **Mutation tools require user confirmation.** TUI confirmation modal for direct commands; LangGraph `interrupt()` for agent-driven mutations.
- **CLI/TUI is the primary mutating interface.** The web dashboard is read-only.
- **Comprehensive AI-authored docs, user-reviewed.** `docs/langchain/`, `docs/langgraph/`, `docs/litellm.md`, `docs/bedrock.md`, `docs/rag.md`, `docs/mcp.md`, `docs/textual.md`, `docs/keycloak.md`, `docs/envoy-gateway.md`, `docs/kubernetes.md`, `docs/nextjs.md`, and `docs/strata/*.md` are written as full references.
- **Hand-written learning notes are welcome** as "What I learned" or "Gotchas" sections in any `docs/` file.
- **One name:** "Strata" everywhere. Old names ("Accio", "Observatory") are banned.

---

## 8. Quick commands

```bash
# Today (Phase 0)
make tui-dev                                # install + run TUI
make tui-test                               # pytest
make reset                                  # nuke .venv / pycache / uv.lock etc. (Phase 0+)

# Phase 1+ (backend on local kind)
make backend-up                             # bring up kind + helm install strata
make backend-down
make backend-logs                           # tail all pods
make backend-rebuild                        # rebuild images + restart
make tui-dev                                # TUI now talks to localhost backend

# Phase 2+ (OIDC)
make keycloak-up                            # admin UI on localhost:8081
make login                                  # TUI device-code flow

# Phase 8+ (real EKS)
cd infra/bootstrap && terraform init && terraform plan
cd backend/helm/strata && helm lint .
```

---

## 9. General guidelines

- **Do not commit changes unless the user explicitly asks.** Verify with `git status` and `git diff` before any commit.
- **Do not skip lint/typecheck.** After any code change, run the relevant linter and `uv run pytest` / `go test ./...` / `pnpm test`.
- **Do not re-litigate locked decisions** (§2). If a decision is wrong, raise it explicitly to the user before changing course.
- **Do not silently delete code.** Use `git rm` so deletions are reviewable.
- **Update `handoff.md` at the end of every working session.** This is the contract between sessions.