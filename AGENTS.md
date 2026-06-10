# AGENTS.md — Strata Platform

> **Read this first.** This file is the source of truth for what Strata is, how it's organized, and the build plan every agent follows. `handoff.md` tracks live state across sessions.

---

## 1. What Strata Is

Strata is a portfolio project that provisions production-grade EKS clusters in an AWS account via GitOps, with a built-in AI co-pilot (LangGraph + LiteLLM) that lets you drive the platform conversationally. The end-state is a multi-tenant SaaS; the **first version is single-user**, running on the author's laptop and managing clusters in the author's own AWS account.

**Two design principles shape the build order:**

1. **The agent is the product; the AWS plumbing is the carrier.** The author is learning LangGraph, LangChain, and RAG by building. The agent loop is built first (Phase 2) against mocked tools, then wired to a real Go orchestrator (Phase 3), then to real AWS (Phase 5).
2. **The CLI is the primary interface; the web UI is for demos.** A senior k8s/AWS engineer reaches for the terminal first. Next.js (App Router) is used because the author can debug it. The web UI is for screenshots and live demos.

**Architecture shape (target end-state):**

```
                 Strata-prod EKS (your account)
                 ┌──────────────────────────────────────────────┐
                 │ Kong Ingress                                  │
                 │   ├─ orchestrator-service (Go)               │
                 │   ├─ provisioner-worker (Go, k8s Job)        │
                 │   ├─ status-poller (Go)                       │
                 │   ├─ argocd-sync (Go)                         │
                 │   ├─ health-monitor (Go)                      │
                 │   ├─ retriever-service (Go) ─► Qdrant        │
                 │   ├─ rag-indexer (Go)                         │
                 │   └─ agent-service (Python: FastAPI +         │
                 │       LangGraph + LangChain) ──► LiteLLM     │
                 │                          └─► Bedrock/OpenAI/ │
                 │                              Anthropic/Ollama│
                 │                              (chat + embed) │
                 │                                              │
                 │ Argo Workflows (replaces Step Functions)     │
                 │ CloudNativePG (Postgres)                     │
                 │ Qdrant (vector store, RAG)                   │
                 │ Redis (in-flight state)                      │
                 │ Zitadel (OIDC, replaces Cognito)             │
                 │ External Secrets Operator ─► AWS Secrets Mgr │
                 │ Prometheus + Grafana + Loki + Tempo          │
                 └──────────────────────────────────────────────┘
                                  │
                                  │ STS AssumeRole
                                  ▼
                 Customer AWS Account (per cluster)
                 ┌──────────────────────────────────────────────┐
                 │ EKS + VPC + ArgoCD + apps from ops repo      │
                 └──────────────────────────────────────────────┘
```

---

## 2. Repo Layout (target — phases 0–1 done; agent sandbox is next)

```
strata/
├── AGENTS.md                       # this file
├── handoff.md                      # live cross-session state
├── README.md                       # human-facing project overview
├── control-plane/                  # k8s manifests + Helm chart for Strata-prod
│   ├── bootstrap/                  # one-time Terraform: VPC, EKS, S3 state, ACM
│   ├── helm/strata/                # umbrella Helm chart
│   └── argocd-apps/                # App-of-apps for the control plane
├── services/                       # Go + Python services (the control plane apps)
│   ├── shared/                     # Go module: db, http, auth, aws, observability
│   ├── orchestrator/               # Go
│   ├── provisioner-worker/         # Go
│   ├── status-poller/              # Go
│   ├── argocd-sync/                # Go
│   ├── health-monitor/             # Go
│   └── agent-service/              # Python (FastAPI + LangGraph + LangChain)
├── workflows/                      # Argo Workflow templates
│   ├── provision-cluster.yaml
│   ├── deprovision-cluster.yaml
│   └── lib/                        # reusable template fragments
├── terraform/
│   └── aws/                        # customer-side EKS module (UNCHANGED)
├── onboarding/                     # CFN template customers deploy
│   ├── strata-platform-role.yaml
│   └── policies/                   # least-privilege IAM (replaces AdministratorAccess)
├── web/                            # Next.js 15 (web frontend, demo interface)
├── mobile/                         # Expo (deferred — Phase 7+)
├── cli/                            # Typer Python CLI (primary interface, Phase 5+)
├── sample-app/                     # sample target app deployed to customer clusters
│   ├── services/                   # 5 Go services (catalog/provisioner/scorecard/workflow/audit)
│   ├── k8s/
│   ├── helm/
│   ├── docker-compose.yml
│   ├── go.work
│   └── AGENTS.md
├── diagrams/                       # PNGs (rebuild later)
├── specs/                          # design docs
│   ├── strata_master_doc.md
│   ├── sample_app_architecture.md
│   └── archives/                   # historical, read-only
├── .github/workflows/              # CI
└── docs/                           # architecture.md, api.md, langgraph-tools.md, etc.
```

---

## 3. Locked Decisions (do not re-litigate)

### Product-shape decisions (added Session 3)

| Concern | Choice | Why |
|---|---|---|
| **Build order** | **Agent first, infrastructure second.** Phase 2 is a working LangGraph agent against mocked tools. Real EKS/AWS wiring lands in Phase 5. | The user wants to *learn* LangGraph and RAG deeply. The agent loop is the product; the AWS plumbing is the carrier. Building infra first means learning the carrier for months before touching the actual subject. |
| **Initial scope** | **Single-user, single-cluster, single AWS account (yours).** Multi-tenant SaaS (Zitadel, CFN onboarding, quotas, billing) is deferred to Phase 6. | Evenings/weekends budget. Real multi-tenant SaaS is 3–5× the work of single-user and would delay any agentic-AI payoff by 6+ months. |
| **Primary interface** | **Python CLI (Typer)** — `strata cluster list`, `strata cluster create`, `strata chat`. The web UI is for demos; the CLI is what you actually use day-to-day. | CLI is a native fit for a k8s/AWS user. It also bypasses the entire web-frontend-debugging surface area. |
| **Doc ownership** | **Comprehensive AI-authored, user-reviewed.** `docs/` contains full references for the entire stack (langchain, langgraph, litellm, bedrock, rag, nextjs) plus project-specific architecture. The user reviews and edits; the AI writes the first draft. | The user asked for comprehensive coverage upfront. Hand-written "What I learned" sections in any doc are welcome as supplemental learning notes. |

### Architecture decisions (from Sessions 1–2, still in force)

| Concern | Choice | Why |
|---|---|---|
| Control plane cluster | **Strata-prod EKS** in our AWS account | Familiar, managed control plane |
| Postgres | **CloudNativePG** operator, in-cluster | Full backup/PITR/failover via operator |
| Customer cluster IaC | **Terraform in a Go subprocess** (reuse `terraform/aws/`) | Lowest migration cost; v1; Crossplane later |
| Auth (Phase 6) | **Zitadel** (or Authentik) self-hosted in-cluster | OSS, full OIDC, no AWS lock-in for auth |
| Agent runtime | **`agent-service` in Python (FastAPI + LangGraph + LangChain)** | Only way to use LangGraph today |
| Model abstraction | **LiteLLM** proxy sidecar | Standard answer; swap providers without code |
| Orchestration (Phase 6) | **Argo Workflows** (replaces Step Functions) | k8s-native, replaces SFN's `waitForTaskToken` |
| Ingress (Phase 6) | **Kong** | Already in `sample-app/docker-compose.yml`; reuse |
| Secrets (Phase 6) | **External Secrets Operator → AWS Secrets Manager** | GitOps-friendly, KMS-backed |
| Observability (Phase 6) | **PLG** (Prometheus, Grafana, Loki, Tempo), in-cluster | OSS, covers metrics/logs/traces |
| Frontend (web) | **Next.js 15 (App Router)** | User can actually debug this. Type-safe server components, file-based routing, RSC streaming for the chat rail. |
| Frontend (mobile) | **Deferred.** Expo/RN scaffolded in a later phase if/when web+CLI+API are stable. | Mobile is the highest-effort, lowest-learning surface for an agentic-AI project. |
| AWS access flow (Phase 5) | **Direct creds in `.env`** (single-user, your own AWS account) | Phases 2–4 are docker-only, no AWS. Phase 5 uses your own account. Cross-account IAM role model lands in Phase 6 (SaaS). |
| AWS access flow (Phase 6) | **Cross-account IAM role only** (CFN onboarding wizard) | No creds in browser; the existing `strata-platform-provisioner` model |
| Co-pilot scope | **Full agent with all tools** + app-level confirmation UX | All tool calls; mutation tools gated by client confirm |
| Vector store (RAG) | **Qdrant** (in-cluster) | Better metadata filtering, hybrid search, easier scale-out path |
| Embedding model (RAG) | **Bedrock Titan Embeddings v2** via LiteLLM | Stays consistent with "all LLM through LiteLLM"; no new vendor |
| RAG scope (v1) | **Platform data + Strata's own `docs/`** | Best ROI for ops-focused co-pilot; logs/incidents deferred |
| RAG ingestion | **Periodic pull** (Go worker) for v1; event-driven deferred | Simple, predictable load; 60s cadence for platform data |
| Reranking | **None** for v1 | Add only if measured recall is low |
| Name | **Strata** (drop "Accio" and "Observatory" entirely) | Single product name everywhere |

---

## 4. Build Phases

The original plan built infrastructure first and the agent last. **This plan inverts that**: the agent loop is built first, against mocked tools, because learning LangGraph and RAG is the point of this project. Real EKS / k8s / cross-account AWS come later, once the agent works.

Phases 0 and 1 are complete (dead-code cleanup + Strata rename). Phases 2–7 are the active backlog.

| # | Phase | Effort | Deps | Status |
|---|---|---|---|---|
| 0 | Delete dead code (Flutter, dead dirs, serverless infra, lambdas, buildspec) | 30 min | — | **DONE** |
| 1 | Rename to Strata across all remaining files | 1–2 h | 0 | **DONE** |
| 2 | **Agent sandbox in Kind.** `services/agent-service/` (Python FastAPI + LangGraph + LangChain + LiteLLM) and a LiteLLM proxy — both as k8s manifests in a local Kind cluster. Five mocked tools. NDJSON streaming `POST /chat`. pytest for the graph. **No docker-compose, no EKS — Kind is the dev target.** | 2–3 weekends | 1 | pending |
| 3 | **Smallest real backend.** Go orchestrator (chi, sqlx, zerolog), Postgres in Docker, shared/ Go module with FakeAWS. `agent-service` tools call the real orchestrator over HTTP. `docker-compose.yml` at repo root. One end-to-end test. | 3–4 weekends | 2 | pending |
| 4 | **RAG end-to-end.** `retriever-service` + `rag-indexer` (Go), Qdrant in Docker, `retrieve_docs` LangChain tool wired into the graph's `retrieve` node, `docs/` written by hand (5–8 short files). | 3–4 weekends | 3 | pending |
| 5 | **Real EKS + bootstrap cluster.** `control-plane/bootstrap/` Terraform, `services/provisioner-worker` + `status-poller` + `argocd-sync` + `health-monitor`. Direct AWS creds in `.env`, single-user against your own AWS account. **`web/` Next.js 15** (3 pages) and **`cli/` Typer Python CLI** as interfaces. | 4–5 weekends | 4 | pending |
| 6 | **SaaS layer.** Zitadel, CFN onboarding wizard + cross-account IAM role, Kong, Argo Workflows (replacing the orchestrator's goroutine), External Secrets Operator, PLG stack. CLI gains `strata login` (OIDC device code). Next.js gets confirmation UX. | 4–5 weekends | 5 | pending |
| 7+ | **Mobile (Expo).** Deferred until web + CLI + API are stable. | TBD | 6 | pending |

**Order:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7+.

**Parallelism note:** within Phase 5, the `web/` (Next.js) and `cli/` (Typer) can be built in parallel after the Go services are working — they consume the same HTTP API. The Go services themselves are best built in the order orchestrator → provisioner-worker → status-poller → argocd-sync → health-monitor, because each one depends on something the previous one wrote to Postgres.

---

## 5. Phase 0 — Delete Dead Code

**Goal:** Remove everything tied to the old serverless architecture and the dead Flutter frontend. The repo is left with `sample-app/`, `terraform/aws/`, the rename targets, and the docs we're about to write.

**Delete:**

- `flutter_app/` — entire directory (web-only Flutter stub, broken string interpolation, no mobile platform dirs)
- `mobileviews/` — 3 mockup PNGs, not load-bearing
- `sampleclientapp/` — 3.4K stale docker-compose, no other content
- `infra_diagram.html` — 53K unreferenced interactive diagram
- `infra/` — entire directory (Lambda/IAM/Cognito/DynamoDB/SFN/CodeBuild/API Gateway TF — replaced by `control-plane/bootstrap/`)
- `lambdas/` — entire directory (Python Lambdas — replaced by Go services in `services/`)
- `buildspec.yml` — CodeBuild spec, replaced by Argo Workflows
- `onboarding_cfn.yaml` — root copy. The role definition is preserved and moved to `onboarding/strata-platform-role.yaml` with `AdministratorAccess` scoped down.

**Keep:**

- `sample-app/` — restructured slightly, see Phase 1
- `terraform/aws/` — the customer-side EKS module, unchanged
- `diagrams/`, `specs/`, `.github/`, `AGENTS.md`, `README.md` — rewritten in Phase 1

**Verification:**

```bash
ls -la
# Should NOT contain: flutter_app, mobileviews, sampleclientapp, infra_diagram.html, infra, lambdas, buildspec.yml, onboarding_cfn.yaml
git status --short
# Should show: AGENTS.md, handoff.md, README.md modified; rest of deletes staged
```

---

## 6. Phase 1 — Rename to Strata

**Goal:** One product name everywhere. Drop "Accio" and "Observatory" entirely.

**Files to touch (representative — find by grep):**

- `AGENTS.md`, `handoff.md`, `README.md` — already being rewritten.
- `sample-app/AGENTS.md` — keep the lint rules section, update branding references.
- `sample-app/go.work` — module paths.
- `sample-app/services/*/go.mod` — module paths.
- `sample-app/services/portal-ui/package.json` — name, title.
- `sample-app/services/portal-ui/index.html` — `<title>`, meta.
- `sample-app/services/portal-ui/src/**/*.jsx` — page titles, brand strings.
- `sample-app/docker-compose.yml` — service names, container names, env vars.
- `sample-app/k8s/base/kustomization.yaml` and overlays — `namePrefix`, image names (`Strata/*` is correct; verify).
- `sample-app/helm/accio-chart/` — **rename directory to `strata-chart/`**. Update `Chart.yaml`, all `app:` selectors, all `metadata.name` fields.
- `sample-app/k8s/base/services/*.yaml` — `app:` labels, ConfigMap names.
- `sample-app/Tiltfile` — resource names, labels.
- `specs/accio_master_doc.md` — rename to `specs/strata_master_doc.md`. Rewrite headers. Keep technical content.
- `specs/sample_app_architecture.md` — same.
- `sample-app/add_go_tests.sh`, `sample-app/github_actions_setup.md`, `sample-app/K8S_SETUP.md` — wording.
- `.github/workflows/*.yml` — workflow names, ECR image paths (`Strata/*` is correct; verify).

**Grep for these patterns and fix:**

```
Accio
accio
Accio-
ACCIO
Observatory
observatory
```

**Note on `Strata` capitalization in Go module paths:** keep lowercase package names per Go conventions, but product-level strings (image names, helm release names, k8s resource names) use `Strata` (capital S, no hyphen).

**Don't touch:** `specs/archives/` (historical, leave as-is).

**Verification:**

```bash
grep -r -i "accio\|observatory" --include="*.go" --include="*.md" --include="*.yml" --include="*.yaml" --include="*.json" --include="*.jsx" --include="*.js" --include="*.ts" --include="*.tsx" .
# Should return only specs/archives/ entries
```

---

## 6.5. RAG (Retrieval-Augmented Generation) — Overview

The Co-Pilot answers questions grounded in Strata's own platform data and docs, not just LLM training data. RAG is **a tool the LangGraph agent calls before answering**, not a system-level wrapper.

### Components

- **Vector store:** Qdrant (in-cluster, single replica for v1, 20Gi PVC). Backup via a CronJob that snapshots to S3. **In Phase 4, Qdrant runs in Docker, not in k8s.** The k8s deployment is part of the Phase 5/6 Helm chart.
- **Embedding model:** Bedrock Titan Embeddings v2 via LiteLLM (`bedrock/amazon.titan-embed-text-v2:0`, 1024-dim). All embedding calls go through LiteLLM — no direct vendor SDKs.
- **Collections (v1):**
  - `strata_clusters` — one chunk per cluster row, metadata `{cluster_id, user_id, status, region, updated_at}`
  - `strata_alerts` — one chunk per alert
  - `strata_workflow_runs` — one chunk per Argo Workflow execution
  - `strata_docs` — one chunk per `docs/` file, metadata `{path, section, sha}`
- **Ingestion (v1, periodic pull):**
  - `rag-indexer` Go service runs every 60s. Reads new/updated rows from Postgres, embeds via LiteLLM, upserts to Qdrant.
  - Docs reindex via a `make reindex-docs` target in Phase 4 (a CronJob / Argo Workflow replaces it in Phase 6).
- **Retrieval:**
  - `retriever-service` Go service, internal ClusterIP. Endpoints: `POST /retrieve`, `POST /index`, `DELETE /index/{collection}/{id}`, `GET /healthz`.
  - Embeds the query via LiteLLM, vector searches Qdrant with optional metadata filters, returns top-k chunks.
  - API key auth via a k8s Secret (Phase 5+); in Phase 4 the API key is in a `.env` file.
- **Agent integration:**
  - `agent-service` (Python) has a `retrieve_docs` LangChain tool that calls the retriever HTTP API. **Wired in Phase 4, not Phase 6** — RAG is part of the agent loop from day one of Phase 4.
  - The LangGraph `retrieve` node runs before `agent`, injecting retrieved context into the LLM prompt.
  - If Qdrant is down, `retrieve_docs` returns `[]` and the agent still answers gracefully (degraded mode, not failure).

### What RAG covers in v1

- **Platform data:** clusters, alerts, workflow runs, pod logs (5-min window aggregates).
- **Docs:** Strata's own `docs/` directory — architecture, onboarding, runbooks, plus curated excerpts of ArgoCD / EKS / AWS troubleshooting.

### What RAG does NOT cover in v1 (deferred)

- **Log/incident search at scale** (Flavor C from the design discussion). Would need reranking, BM25+vector hybrid search at volume. Defer until measured recall is poor.
- **Event-driven ingestion.** Periodic pull is fine for v1 cadence.
- **Reranking.** Add Cohere Rerank or BGE-reranker only if measured answer quality is low.

### Cross-cutting rule

> **RAG goes through the retriever-service.** No service other than `retriever-service` and `rag-indexer` may talk to Qdrant directly. This centralizes the embedding model and lets us swap vector stores without touching consumers.

---

## 7. What's Coming in Phases 2+ (reference, not for execution yet)

### Phase 2 — Agent sandbox in Kind (`services/agent-service/` + k8s manifests)

A working LangGraph agent you can talk to, that calls mocked tools, that you fully understand. **Everything runs in a local Kind cluster from day one** — no docker-compose, no EKS, no auth, no production plumbing. Just k8s manifests, kind, kubectl port-forward, and curl.

- **Repo layout:**
  ```
  control-plane/
    manifests/                          # raw k8s manifests (no Helm in Phase 2)
      00-namespace.yaml
      10-litellm/
        deployment.yaml
        service.yaml
        configmap.yaml                  # model list, region
        secret.yaml.example             # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (gitignored)
      20-agent-service/
        deployment.yaml
        service.yaml
  strata-dev-kind.yaml                  # kind cluster config (port mappings, registry)
  Makefile                              # make kind-up / kind-down / apply / logs / chat
  services/agent-service/
    pyproject.toml                      # uv-managed
    Dockerfile                          # python:3.12-slim, uv sync, uvicorn
    app/
      __init__.py
      main.py                           # FastAPI, POST /chat streams NDJSON
      graph.py                          # LangGraph state machine
      state.py                          # typed state
      providers/
        litellm_provider.py             # calls http://litellm:4000/v1/chat/completions
      tools/
        list_clusters.py                # @tool, returns Pydantic model
        get_cluster_status.py
        get_cluster_logs.py
        provision_cluster.py
        delete_cluster.py
    tests/
      test_graph.py                     # asserts correct tool called for given prompt
      test_tools.py
    README.md
  docs/
    langgraph-tools.md                  # AI-written; user reviews and edits
    strata/
      agent-architecture.md             # AI-written; user reviews and edits
  ```
- **Graph (Phase 2, minimal):** `think` → `tool_call` (if any) → `respond`. No checkpointer, no confirmation flow, no RAG node. Pure in-memory.
- **Tools (Phase 2, all mocked):** each is a `@tool`-decorated function returning a Pydantic model. Hardcoded JSON. No HTTP calls.
- **LiteLLM:** runs as a Deployment in the `strata` namespace. Configured with `bedrock/amazon.nova-pro-v1:0` (chat) and `bedrock/amazon.titan-embed-text-v2:0` (embed, for Phase 4). AWS creds come from a k8s Secret — **not IRSA** (IRSA only works on real EKS, not Kind). The secret is in `secret.yaml.example` and copied to a real (gitignored) `secret.yaml`. The agent-service provider module calls `http://litellm:4000/v1/chat/completions` (in-cluster DNS).
- **Kind cluster:** `strata-dev-kind.yaml` provisions a single-node cluster with port mappings: `30000 → 3000` (UI later), `30800 → 8080` (agent-service). Local registry on `localhost:5000` for image builds.
- **Dev loop:** `make kind-up && make build && make apply && make chat`. Iterating: `make build-agent && make apply-agent && make chat`. No docker-compose. The same k8s manifests will deploy to EKS in Phase 5.
- **Streaming:** NDJSON, one JSON object per line: `{"type": "token", "text": "..."}`, `{"type": "tool_call", "name": "list_clusters", "args": {}}`, `{"type": "tool_result", "name": "list_clusters", "result": [...]}, {"type": "done"}`. Not SSE — easier to debug from `curl`.
- **Tests (pytest):** run inside the cluster, not in CI yet. At minimum: (1) given prompt "list my clusters", graph calls `list_clusters` tool; (2) tool result is included in next LLM call; (3) streaming emits `done` exactly once.
- **Docs:** `docs/langgraph-tools.md` is the AI-written reference; the user reviews and edits. See `docs/langgraph.md` for the canonical reference.

### Phase 3 — Smallest real backend (`services/orchestrator/` + `services/shared/`)

`agent-service` tools call a real Go orchestrator over HTTP. Postgres in Docker. AWS calls stubbed.

- **`services/shared/` Go module:**
  - `db` (sqlx, migrations)
  - `http` (chi, zerolog, otel init, recovery middleware)
  - `auth` — `MOCK_USER` middleware that reads `X-Strata-User-Id` from the request header. Zitadel lands in Phase 6.
  - `awsiface` — interface + `FakeAWS` impl (in-memory state machine; 5s fake "CREATING" → "ACTIVE" goroutine).
  - `litellm` — thin HTTP client (not actually used by orchestrator; this is for future RAG work).
- **`services/orchestrator/`:**
  - Endpoints: `POST /clusters`, `GET /clusters`, `GET /clusters/{id}`, `DELETE /clusters/{id}`, `GET /dashboard/summary`, `PUT /users/me/github-token`.
  - Persists to Postgres (sqlx). On `POST /clusters`, inserts a row (`status=INITIATED`) and kicks a goroutine that drives `awsiface.FakeAWS` to `ACTIVE` in ~5s.
  - `agent-service` tools updated to `httpx.post("http://localhost:8080/clusters", ...)` instead of returning mocks.
- **`docker-compose.yml` at repo root:** postgres, orchestrator, agent-service, litellm.
- **One end-to-end test:** `curl -X POST /agent/chat -d '{"message":"list my clusters"}'` returns a mention of the seeded cluster.
- **Docs:** `docs/strata/agent-architecture.md` updated with the real HTTP flow (Mermaid diagram). See the Mermaid diagram in the existing doc.

### Phase 4 — RAG end-to-end (`services/retriever-service/`, `services/rag-indexer/`, Qdrant)

The agent answers questions grounded in Strata's own docs and platform data. All in Docker, no k8s.

- **`services/retriever-service/`** (Go, chi):
  - `POST /retrieve` — body `{collection, query, top_k, filter}`, returns top-k chunks with metadata + score.
  - `POST /index` — body `{collection, id, text, metadata}`, embeds + upserts.
  - `DELETE /index/{collection}/{id}` — removes a chunk.
  - `GET /healthz` — readiness.
  - Embeddings via `http://litellm:4000/v1/embeddings` (Bedrock Titan v2, 1024-dim).
  - Qdrant client: `github.com/qdrant/go-client`.
  - API key auth via env var (Phase 4); k8s Secret in Phase 5.
- **`services/rag-indexer/`** (Go):
  - 30s ticker reads `clusters` table, embeds, upserts to `strata_clusters` collection.
  - One chunk per cluster row. Metadata `{cluster_id, user_id, status, region, updated_at}`.
  - `make reindex-docs` target walks `docs/`, chunks by header, embeds, upserts to `strata_docs` collection.
- **`agent-service` graph update:** add a `retrieve` node before `think`. Conditional routing: if user message contains a "what/how" question or matches a doc-keyword regex, call `retrieve_docs` first; otherwise skip.
- **`docs/` directory:** `docs/strata/`, `docs/argo-cd/`, `docs/eks/`. AI writes 5–8 short docs; the user reviews and edits. The point is (a) having something to index and (b) learning what good chunk boundaries look like. The `docs/strata/agent-architecture.md` reference already exists; the RAG-relevant additions are project-specific runbooks, not the reference docs themselves.
- **`docker-compose.yml` additions:** Qdrant (single node, persistent volume), retriever-service, rag-indexer.
- **Docs:** `docs/rag.md` is the AI-written reference. The user reviews and adds "What I learned" notes.

### Phase 5 — Real EKS + bootstrap cluster + Next.js + CLI

`terraform/aws/` actually runs. Strata-prod EKS comes up in your own AWS account. Single-user, hardcoded creds in `.env`. The Next.js web UI and Typer CLI land in this phase.

- **`control-plane/bootstrap/`** (Terraform):
  - VPC (3 AZs, public + private subnets, NAT)
  - EKS 1.29+ with managed node group
  - S3 bucket for TF state + DynamoDB lock table
  - KMS key
  - ACM cert
  - IRSA roles for LiteLLM, External Secrets, Argo
  - Outputs: cluster name, endpoint, kubeconfig, role ARNs
- **Go services wired to real AWS:**
  - `provisioner-worker` — k8s Job that wraps `terraform apply` against the `terraform/aws/` module. **For v1, "the customer account" is your own AWS account.** No STS, no external ID. Direct creds via IRSA on the Strata-prod cluster.
  - `status-poller` — polls `eks:DescribeCluster`, updates Postgres.
  - `argocd-sync` — watches Postgres, calls ArgoCD API on the provisioned cluster to register the ops-repo app.
  - `health-monitor` — periodic checks, writes `alerts` table.
  - **Argo Workflows deferred.** Phase 5 uses a Go orchestrator-triggered goroutine to drive provision/deprovision. Swap in Argo in Phase 6.
- **`web/` (Next.js 15, App Router):**
  - 3 pages: `/` (cluster list), `/clusters/$id` (status + logs), `/chat` (copilot).
  - Server actions call the orchestrator. No TanStack, no MobX, no client-side state library.
  - Confirmation UX for mutation tools lands here in minimal form (an `<Alert />` + buttons).
- **`cli/` (Python, Typer):**
  - `strata cluster list`, `strata cluster get`, `strata cluster create`, `strata cluster delete`.
  - `strata chat` — streaming REPL that calls `POST /agent/chat`, prints tokens as they arrive.
  - `strata config` — show/set API URL, API token, default region.
  - Reuses the same `httpx` HTTP client the agent uses internally.
  - This is your **primary day-to-day interface**. The web UI is for demos.
- **End-to-end test:** `docker-compose up` → `strata cluster create demo --region us-west-2` → wait → `strata cluster list` shows `READY` → `strata chat "what's the status of demo?"` → answer.
- **Docs:** `docs/eks-onboarding.md`, `docs/strata/control-plane.md` — AI-written, user-reviewed. The reference `docs/bedrock.md`, `docs/nextjs.md` already cover the EKS and Next.js surfaces.

### Phase 6 — SaaS layer (multi-tenant, production-grade infra)

Turn the single-user system into a multi-tenant SaaS. This is where Zitadel, CFN onboarding, Kong, External Secrets, Argo Workflows, and the proper IRSA story land.

- **Zitadel** replaces the `MOCK_USER` middleware. OIDC discovery URL in `.env`. CLI gains `strata login` (OIDC device code flow, works on a headless box).
- **CFN onboarding wizard:** `onboarding/strata-platform-role.yaml` (already there) becomes a real downloadable template. `POST /onboarding/verify-role` actually does STS assume-role.
- **Kong** in front of the orchestrator. Rate limiting, request validation.
- **Argo Workflows** replaces the orchestrator's goroutine. WorkflowTemplates for `provision-cluster` and `deprovision-cluster`.
- **External Secrets Operator** in Strata-prod, AWS Secrets Manager for GitHub tokens, LiteLLM keys, Qdrant key.
- **PLG stack** installed (Prometheus, Grafana, Loki, Tempo).
- **Next.js UI** gets the onboarding wizard, the cluster-create form, and the right-rail `<CopilotRail />` with the `<ToolCallCard />` confirmation UX (allow once / always allow / deny).
- **CLI:** `strata login`, `strata cluster create` (interactive prompts).
- **Smoke test in CI:** `kind`-based e2e that runs the full flow against a mocked AWS.

### Phase 7+ — Mobile (Expo)

Deferred. Add when web + CLI + API are stable. Expo Router mirroring `web/`, Zitadel auth via `expo-auth-session` + `expo-web-browser`, token storage in `expo-secure-store`.

---

## 8. API Surface (frozen, for the rewrite)

The 7 routes from the old API Gateway carry over. The frontend, the CLI, and (in Phase 6) the Argo workflows hit them via Kong.

| Method | Path | Owner service | Purpose |
|---|---|---|---|
| POST | `/clusters` | orchestrator | Provision a new cluster. Kicks Argo Workflow (Phase 6+; Phase 5 uses a goroutine). |
| GET | `/clusters` | orchestrator | List user's clusters. |
| GET | `/clusters/{id}` | orchestrator | Fast status poll. |
| DELETE | `/clusters/{id}` | orchestrator | Deprovision. Kills Argo Workflow if running, then runs `deprovision-cluster`. |
| GET | `/dashboard/summary` | orchestrator | Aggregate counts by status. |
| POST | `/agent/chat` | agent-service | Streamed chat with the Co-Pilot. NDJSON in Phase 2–4, SSE in Phase 5+ when the web UI needs it. |
| PUT | `/users/me/github-token` | orchestrator | Persist GitHub token (used for ops-repo access). |

Plus internal routes (not exposed via Kong, only within the cluster):
- `PATCH /internal/clusters/{id}/status` — called by Argo Workflows (Phase 6+) or the orchestrator's goroutine (Phase 5) to update status.
- `POST /internal/onboarding/verify` — STS assume-role verification helper. **Phase 6 only** (single-user in Phase 5, no cross-account role).
- `POST /retrieve`, `POST /index`, `DELETE /index/{collection}/{id}` — `retriever-service`. Internal ClusterIP, called only by `agent-service` and `rag-indexer`.

---

## 9. Naming Conventions

- **Product name:** `Strata` (capital S, no hyphen) in all user-facing strings and code identifiers where the brand appears.
- **Helm release name:** `strata`.
- **K8s namespace:** `strata`.
- **ECR repository prefix:** `strata/`.
- **Go module path:** `github.com/strata/<service-name>` (lowercase per Go convention).
- **Python packages:** `strata_agent_service` (FastAPI service), `strata_cli` (Typer CLI).
- **CLI command:** `strata` (invoked as `strata cluster list`, `strata chat`, etc.).

---

## 10. Cross-cutting Rules

- **No docker-compose for the platform.** The platform (Phase 2+) ships as k8s manifests from day one. Dev runs against a local Kind cluster. The same manifests deploy to EKS in Phase 5+. `docker-compose.yml` is only for the `sample-app/`, not the platform.
- **No AWS serverless in the new control plane.** No Lambda, no Step Functions, no API Gateway, no DynamoDB, no CodeBuild. Anything that would have been a Lambda is a Go service or a Python service. Anything that would have been Step Functions is an Argo Workflow.
- **No Cognito.** Use Zitadel (Phase 6).
- **No Flutter, no React Native CLI.** Web is Next.js 15 (App Router). Mobile is Expo, deferred.
- **No `AdministratorAccess` in cross-account roles.** Scope down per `onboarding/policies/*.json`.
- **All LLM calls go through LiteLLM.** `agent-service` never imports a vendor SDK directly.
- **All embeddings go through LiteLLM.** The retriever-service calls `http://litellm:4000/v1/embeddings`, never a vendor SDK directly.
- **All RAG retrieval goes through `retriever-service`.** `agent-service` and any other consumer call the retriever HTTP API, never Qdrant directly. Centralizes embedding-model choice and makes it swappable.
- **All long-lived secrets come from External Secrets.** No `Secret` resources in Helm with literal values.
- **All cluster-to-cluster auth is OIDC + JWT.** No shared static API keys between Strata and customer clusters.
- **Mutation tools in the agent require user confirmation.** Gate at the application layer; do not rely on Bedrock's native confirmation (limited UX).
- **Build the agent loop against mocked infra first.** The agent is the product; the AWS plumbing is the carrier. Phase 2 = mocked tools. Don't touch real EKS until the agent works.
- **CLI is a first-class interface, not an afterthought.** The Typer CLI (`strata cluster ...`, `strata chat`) is what the user actually runs day-to-day. The web UI is for demos. Both consume the same HTTP API; both ship in Phase 5.
- **Comprehensive AI-authored docs, user-reviewed.** `docs/langchain.md`, `docs/langgraph.md`, `docs/litellm.md`, `docs/bedrock.md`, `docs/rag.md`, `docs/nextjs.md`, and `docs/strata/agent-architecture.md` are written as full references for the technology stack and how Strata uses it. The user reviews and edits; the AI writes the first draft. Hand-written learning notes can live in the same files as "What I learned the hard way" sections.
- **Hand-written learning notes are welcome** in any `docs/` file as a "What I learned" or "Gotchas" section. The act of writing forces the learning, but it does not need to be the *only* way to learn.
- **One name:** "Strata" everywhere. "Accio" and "Observatory" are banned.

---

## 11. Quick Commands (current and future)

```bash
# Today (Phases 0–1)
ls -la                                           # verify Phase 0 deletions
grep -r -i "accio\|observatory" --include="*" .  # verify Phase 1 rename
git status --short                               # see what's staged

# Phase 2 (agent sandbox) — coming next
make kind-up                                       # create Kind cluster + local registry
make build                                         # build agent-service image, push to localhost:5000
make apply                                         # apply manifests in control-plane/manifests/
make chat                                          # port-forward + curl /chat
make logs-agent                                    # tail agent-service logs
make kind-down                                     # delete the dev cluster

# Phase 3+ (smallest real backend, then RAG, then real EKS)
make kind-up && make apply                         # adds postgres + orchestrator manifests
cd services/orchestrator && go test ./...
cd services/retriever-service && go test ./...
cd services/agent-service && uv run pytest         # tests run inside the cluster
cd cli && uv run strata cluster list               # CLI added in Phase 5
cd web && pnpm dev                                  # Next.js added in Phase 5

# Phase 5+ (real EKS, bootstrap, SaaS)
cd control-plane/bootstrap && terraform init && terraform plan
cd control-plane/helm/strata && helm lint .

# Local sample app dev (unchanged)
docker-compose -f sample-app/docker-compose.yml up
kind create cluster && cd sample-app && tilt up
```

---

## 12. General Guidelines

- **Do not commit changes unless the user explicitly asks.** Verify with `git status` and `git diff` before any commit.
- **Do not skip lint/typecheck.** After any code change, run the relevant linter and `go test` / `pnpm test` / `uv run pytest`.
- **Do not re-litigate locked decisions** (Section 3). If a decision is wrong, raise it explicitly to the user before changing course.
- **Do not silently delete code.** If a file is being removed as part of dead-code cleanup, prefer `git rm` so the deletion is reviewable.
- **Update `handoff.md` at the end of every working session.** This is the contract between sessions.
