# AGENTS.md — Strata Platform

> **Read this first.** This file is the source of truth for what Strata is, how it's organized, and the build plan every agent follows. `handoff.md` tracks live state across sessions.

---

## 1. What Strata Is

Strata is a SaaS that provisions production-grade EKS clusters in customer AWS accounts. The user connects a GitHub ops repo and an AWS account; Strata creates an EKS cluster in that account, installs ArgoCD, and syncs the cluster from the ops repo. A right-rail AI Co-Pilot (LangGraph + LiteLLM) lets users drive the platform conversationally.

**Architecture shape (target):**

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

## 2. Repo Layout (target — phases 0–1 partially complete)

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
├── web/                            # TanStack Start (web frontend)
├── mobile/                         # Expo (React Native)
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

| Concern | Choice | Why |
|---|---|---|
| Control plane cluster | **Strata-prod EKS** in our AWS account | Familiar, managed control plane |
| Postgres | **CloudNativePG** operator, in-cluster | Full backup/PITR/failover via operator |
| Customer cluster IaC | **Terraform in a Go subprocess** (reuse `terraform/aws/`) | Lowest migration cost; v1; Crossplane later |
| Auth | **Zitadel** (or Authentik) self-hosted in-cluster | OSS, full OIDC, no AWS lock-in for auth |
| Agent runtime | **`agent-service` in Python (FastAPI + LangGraph + LangChain)** | Only way to use LangGraph today |
| Model abstraction | **LiteLLM** proxy sidecar | Standard answer; swap providers without code |
| Orchestration | **Argo Workflows** (replaces Step Functions) | k8s-native, replaces SFN's `waitForTaskToken` |
| Ingress | **Kong** | Already in `sample-app/docker-compose.yml`; reuse |
| Secrets | **External Secrets Operator → AWS Secrets Manager** | GitOps-friendly, KMS-backed |
| Observability | **PLG** (Prometheus, Grafana, Loki, Tempo), in-cluster | OSS, covers metrics/logs/traces |
| Frontend (web) | **TanStack Start** | Type-safe loaders, file-based routing, great for dashboards |
| Frontend (mobile) | **Expo (React Native) + Expo Router** | JS/TS continuity with web; native iOS/Android |
| AWS access flow | **Cross-account IAM role only** (CFN onboarding wizard) | No creds in browser; the existing `strata-platform-provisioner` model |
| Co-pilot scope | **Full agent with all tools** + app-level confirmation UX | All tool calls; mutation tools gated by client confirm |
| Vector store (RAG) | **Qdrant** (in-cluster) | Better metadata filtering, hybrid search, easier scale-out path |
| Embedding model (RAG) | **Bedrock Titan Embeddings v2** via LiteLLM | Stays consistent with "all LLM through LiteLLM"; no new vendor |
| RAG scope (v1) | **Platform data + Strata's own `docs/`** | Best ROI for ops-focused co-pilot; logs/incidents deferred |
| RAG ingestion | **Periodic pull** (Go worker) for v1; event-driven deferred | Simple, predictable load; 60s cadence for platform data |
| Reranking | **None** for v1 | Add only if measured recall is low |
| Name | **Strata** (drop "Accio" and "Observatory" entirely) | Single product name everywhere |

---

## 4. Build Phases

| # | Phase | Effort | Deps | Status |
|---|---|---|---|---|
| 0 | Delete dead code (Flutter, dead dirs, serverless infra, lambdas, buildspec) | 30 min | — | **DONE** |
| 1 | Rename to Strata across all remaining files | 1–2 h | 0 | **DONE** |
| 2 | Bootstrap the control-plane EKS cluster (`control-plane/bootstrap/`) | 1–2 d | 0, 1 | pending |
| 3 | Helm umbrella chart + install Kong, CloudNativePG, Zitadel, LiteLLM, Argo, PLG, cert-manager, External Secrets, **Qdrant** | 1 wk | 2 | pending |
| 4 | Go services: orchestrator, provisioner-worker, status-poller, argocd-sync, health-monitor, **retriever-service, rag-indexer**; SQL migrations | 1.5 wk | 3 | pending |
| 5 | Argo Workflow templates (`provision-cluster`, `deprovision-cluster`) | 2–3 d | 4 | pending |
| 6 | `agent-service` (Python/FastAPI + LangGraph + LangChain + LiteLLM) — **includes `retrieve_docs` tool** | 1 wk | 4 | pending |
| 7 | `web/` TanStack Start: dashboard, onboarding wizard, copilot rail, tool confirmation, Zitadel auth | 2–3 d | 4 (API), 6 (for /agent/chat) | pending |
| 8 | `mobile/` Expo scaffold + chat route + onboarding wizard + Zitadel auth | 1–2 d | 4 (API) | pending |
| 9 | End-to-end: deploy CFN → verify role → provision a real cluster → see READY → chat with agent | 3–4 d | All | pending |
| 10 | Polish: secrets scan, helm lint, kubeconform, smoke tests in CI | 2 d | 4 | pending |

**Order:** 0 → 1 → 2 → 3 → 4 → (5 ‖ 6) → (7 ‖ 8) → 9 → 10.

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

- **Vector store:** Qdrant (in-cluster, single replica for v1, 20Gi PVC). Backup via a CronJob that snapshots to S3.
- **Embedding model:** Bedrock Titan Embeddings v2 via LiteLLM (`bedrock/amazon.titan-embed-text-v2:0`, 1024-dim). All embedding calls go through LiteLLM — no direct vendor SDKs.
- **Collections (v1):**
  - `strata_clusters` — one chunk per cluster row, metadata `{cluster_id, user_id, status, region, updated_at}`
  - `strata_alerts` — one chunk per alert
  - `strata_workflow_runs` — one chunk per Argo Workflow execution
  - `strata_docs` — one chunk per `docs/` file, metadata `{path, section, sha}`
- **Ingestion (v1, periodic pull):**
  - `rag-indexer` Go service runs every 60s. Reads new/updated rows from Postgres, embeds via LiteLLM, upserts to Qdrant.
  - Docs reindex via an Argo Workflow triggered on push to `docs/**` and weekly as a backstop.
- **Retrieval:**
  - `retriever-service` Go service, internal ClusterIP. Endpoints: `POST /retrieve`, `POST /index`, `DELETE /index/{collection}/{id}`, `GET /healthz`.
  - Embeds the query via LiteLLM, vector searches Qdrant with optional metadata filters, returns top-k chunks.
  - API key auth via a k8s Secret.
- **Agent integration:**
  - `agent-service` (Python) has a `retrieve_docs` LangChain tool that calls the retriever HTTP API.
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

### Phase 2 — `control-plane/bootstrap/`

One-time Terraform that creates the Strata-prod EKS cluster.

- VPC (3 AZs, public + private subnets, NAT)
- EKS 1.29+ with managed node group
- S3 bucket for Terraform state + DynamoDB lock table
- KMS key for encryption
- ACM certificate (or external-dns + Let's Encrypt)
- IRSA roles for the major workloads (LiteLLM, External Secrets, Argo)
- Outputs: cluster name, cluster endpoint, kubeconfig command, role ARNs

### Phase 3 — `control-plane/helm/strata/`

Umbrella chart with subcharts/deps for:
- Kong (Ingress)
- CloudNativePG (Postgres)
- Zitadel (OIDC)
- LiteLLM (model proxy)
- Argo Workflows
- ArgoCD (for the control plane itself)
- cert-manager
- External Secrets Operator
- Prometheus + Grafana + Loki + Tempo (kube-prometheus-stack + Loki + Tempo)
- **Qdrant** (vector store for RAG, single replica + 20Gi PVC + S3 snapshot backup)

Plus templates for the 7 Go services and the Python `agent-service`.

### Phase 4 — `services/`

**Go services (chi router, sqlx, zerolog, otel):**

- `orchestrator` — HTTP API. `POST/GET/DELETE /clusters`, `GET /dashboard/summary`, `PUT /users/me/github-token`, `POST /onboarding/verify-role`. Persists to Postgres. Kicks Argo Workflow for provision/deprovision. Verifies Zitadel JWTs.
- `provisioner-worker` — k8s Job that runs Terraform. Invoked by Argo Workflows. Wraps `terraform` binary. STS assume-role into customer account.
- `status-poller` — long-running Deployment with a ticker. Polls customer EKS APIs, updates Postgres.
- `argocd-sync` — long-running. Watches Postgres for new clusters, calls customer ArgoCD API to register the ops-repo app.
- `health-monitor` — long-running. Periodic health checks, writes `alerts` table.
- `retriever-service` — internal HTTP API. Endpoints `POST /retrieve`, `POST /index`, `DELETE /index/{collection}/{id}`, `GET /healthz`. Embeds via LiteLLM, vector searches Qdrant. API key auth.
- `rag-indexer` — periodic pull worker (60s). Reads new/updated rows from Postgres (clusters, alerts, workflow runs), embeds via LiteLLM, upserts to Qdrant. One chunk per row; metadata for filtered retrieval.

**`shared/` Go module:** Postgres client, Zitadel JWT verifier, STS helpers, otel init, common types, HTTP middleware, Qdrant client factory, LiteLLM HTTP client.

**`agent-service` (Python):** FastAPI on `:8080`. Endpoint `POST /agent/chat` streams SSE. LangGraph state machine with Postgres checkpointer. LangChain tools for: `list_clusters`, `get_cluster_status`, `get_cluster_logs`, `provision_cluster`, `delete_cluster`, **`retrieve_docs`** (RAG — calls `retriever-service`). Mutation tools carry `requires_confirmation=True` — the graph's `confirm` node calls `ConfirmationStore` (Postgres) and the web/mobile client resolves the prompt and posts back.

### Phase 5 — `workflows/`

- `provision-cluster.yaml` — Argo WorkflowTemplate: assume-role → write-status(PROVISIONING) → terraform-apply → eks-wait-active → write-status(READY).
- `deprovision-cluster.yaml` — mirror with `terraform destroy`.
- `lib/` — reusable template fragments: `assume-role`, `terraform-apply`, `eks-wait-active`, `write-status`.

### Phase 6 — `agent-service` details

- `app/main.py` — FastAPI app, `/agent/chat` SSE endpoint.
- `app/graph.py` — LangGraph state machine (see plan in `handoff.md`).
- `app/tools/*.py` — LangChain tool definitions.
- `app/providers/litellm_provider.py` — thin adapter; `agent-service` only ever talks to LiteLLM's OpenAI-compatible API.
- `app/persistence.py` — LangGraph `PostgresSaver`.
- `app/confirmation.py` — Postgres-backed `ConfirmationStore` keyed by `(thread_id, tool_call_id)`.

### Phase 7 — `web/` (TanStack Start)

- File-based routes: `/login`, `/callback`, `/` (dashboard), `/clusters/new`, `/clusters/$id`, `/settings`, `/chat` (mobile-web full-page), `/onboarding/*`.
- `<CopilotProvider>` wraps `__root.tsx`; right-rail `<CopilotRail />` on `lg:`, full-page on mobile-web.
- `<ToolCallCard />` with **Allow once / Always allow / Deny** buttons for mutation tools.
- Zitadel auth via `oidc-client-ts` (or `react-oidc-context` pointed at Zitadel's discovery URL).
- API client in `app/api/client.ts` — single `fetch` wrapper that attaches Zitadel ID token, validates responses with Zod.
- 7 routes total (matches the API surface from the old spec — see `handoff.md` §API surface).

### Phase 8 — `mobile/` (Expo)

- Expo Router file-based routes mirroring `web/`.
- Zitadel auth via `expo-auth-session` + `expo-web-browser`.
- Token storage in `expo-secure-store`.
- API client duplicates `web/src/api/` for v1 (will consolidate to a shared package later).

---

## 8. API Surface (frozen, for the rewrite)

The 7 routes from the old API Gateway carry over. The frontend and the Argo workflows hit them via Kong.

| Method | Path | Owner service | Purpose |
|---|---|---|---|
| POST | `/clusters` | orchestrator | Provision a new cluster. Kicks Argo Workflow. |
| GET | `/clusters` | orchestrator | List user's clusters. |
| GET | `/clusters/{id}` | orchestrator | Fast status poll. |
| DELETE | `/clusters/{id}` | orchestrator | Deprovision. Kills Argo Workflow if running, then runs `deprovision-cluster`. |
| GET | `/dashboard/summary` | orchestrator | Aggregate counts by status. |
| POST | `/agent/chat` | agent-service | Streamed chat with the Co-Pilot (SSE). |
| PUT | `/users/me/github-token` | orchestrator | Persist GitHub token (used for ops-repo access). |

Plus internal routes (not exposed via Kong, only within the cluster):
- `PATCH /internal/clusters/{id}/status` — called by Argo Workflows to update status.
- `POST /internal/onboarding/verify` — STS assume-role verification helper.

---

## 9. Naming Conventions

- **Product name:** `Strata` (capital S, no hyphen) in all user-facing strings and code identifiers where the brand appears.
- **Helm release name:** `strata`.
- **K8s namespace:** `strata`.
- **ECR repository prefix:** `strata/`.
- **Go module path:** `github.com/strata/<service-name>` (lowercase per Go convention).
- **Python package:** `strata_agent_service`.

---

## 10. Cross-cutting Rules

- **No AWS serverless in the new control plane.** No Lambda, no Step Functions, no API Gateway, no DynamoDB, no CodeBuild. Anything that would have been a Lambda is a Go service or a Python service. Anything that would have been Step Functions is an Argo Workflow.
- **No Cognito.** Use Zitadel.
- **No Flutter, no React Native CLI.** Web is TanStack Start, mobile is Expo.
- **No `AdministratorAccess` in cross-account roles.** Scope down per `onboarding/policies/*.json`.
- **All LLM calls go through LiteLLM.** `agent-service` never imports a vendor SDK directly.
- **All embeddings go through LiteLLM.** The retriever-service calls `http://litellm:4000/v1/embeddings`, never a vendor SDK directly.
- **All RAG retrieval goes through `retriever-service`.** `agent-service` and any other consumer call the retriever HTTP API, never Qdrant directly. Centralizes embedding-model choice and makes it swappable.
- **All long-lived secrets come from External Secrets.** No `Secret` resources in Helm with literal values.
- **All cluster-to-cluster auth is OIDC + JWT.** No shared static API keys between Strata and customer clusters.
- **Mutation tools in the agent require user confirmation.** Gate at the application layer; do not rely on Bedrock's native confirmation (limited UX).
- **One name:** "Strata" everywhere. "Accio" and "Observatory" are banned.

---

## 11. Quick Commands (current and future)

```bash
# Today (Phases 0–1)
ls -la                                           # verify Phase 0 deletions
grep -r -i "accio\|observatory" --include="*" .  # verify Phase 1 rename
git status --short                               # see what's staged

# Later (Phase 2+)
cd control-plane/bootstrap && terraform init && terraform plan
cd control-plane/helm/strata && helm lint .
cd services/orchestrator && go test ./...
cd services/agent-service && uv run pytest

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
