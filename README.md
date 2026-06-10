# Strata

Strata is a portfolio project: a platform that provisions production-grade EKS clusters in your AWS account via GitOps, with an AI co-pilot you drive conversationally. The catch — and the point — is that **the agent is the product, not the AWS plumbing**. The control plane is the carrier.

**What's here right now:** documentation, the rename to "Strata" across the repo, and a sample Go microservices app (`sample-app/`) that runs locally in Docker. The agent, the real backend, RAG, and the EKS bootstrap all come next, in that order.

**What's coming:** a working LangGraph agent running in a local Kind cluster (Phase 2), then a real Go orchestrator behind it (Phase 3), then RAG (Phase 4), then the actual EKS bootstrap and a CLI you can drive day-to-day (Phase 5). The multi-tenant SaaS layer (Zitadel, CFN onboarding, cross-account IAM, Kong, Argo Workflows) is Phase 6. Mobile is deferred. **No docker-compose for the platform** — k8s manifests from day one, Kind as the dev target, the same manifests deploy to EKS in Phase 5.

---

## Why This Project Exists

The author is a senior AWS + Kubernetes engineer who knows LangGraph, RAG, and the modern Python agentic-AI stack only by reputation. This project is the vehicle for learning those things by building a real thing end-to-end — not by reading docs, not by following tutorials.

Three constraints shape the design:

1. **Evenings and weekends only.** Anything that takes more than 4–5 weekends to ship a working demo is cut.
2. **No frontend debugging capacity.** Next.js (App Router) is the only frontend. The Typer-based Python CLI is the primary day-to-day interface. The web UI is for demos.
3. **Single-user first.** A real multi-tenant SaaS is the long-term goal, but Phase 6 work, not Phase 1. The first version is "Strata runs on your laptop and manages clusters in your own AWS account."

These three constraints are why the build order is **agent-first, infrastructure-second**. The agent loop is what we want to learn. Real EKS wiring is the mechanical part that comes after.

---

## Architecture (target)

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

This is the **end-state**. The repo today is the sample app + docs. We get to this picture by walking the phases in `AGENTS.md §4`.

---

## Repository Layout

```
strata/
├── AGENTS.md            # source of truth for the plan
├── handoff.md           # live state across sessions
├── README.md            # this file
├── control-plane/       # Helm chart + bootstrap Terraform for Strata-prod (Phase 5+)
├── services/            # Go and Python control-plane services (Phase 2+)
├── cli/                 # Python Typer CLI (Phase 5+ — primary interface)
├── web/                 # Next.js 15 (Phase 5+ — demo interface)
├── workflows/           # Argo Workflow templates (Phase 6+)
├── terraform/aws/       # customer-side EKS module (the real IaC)
├── onboarding/          # CloudFormation template customers deploy (Phase 6+)
├── sample-app/          # sample target app deployed to customer clusters (works today)
├── diagrams/            # architecture diagrams (to be redrawn)
├── specs/               # design documents
├── .github/workflows/   # CI
└── docs/                # architecture, RAG, agent reference (Phase 2+)
```

---

## How It Works (target end-state)

### Provisioning a cluster

1. User runs `strata cluster create demo --region us-west-2` from the CLI (or fills out the form in the web UI).
2. `orchestrator-service` writes a row to Postgres (`status=INITIATED`) and kicks a goroutine (Phase 5) or Argo Workflow (Phase 6+) that runs `terraform/aws/` against the user's AWS account.
3. EKS comes up, ArgoCD is installed, the user's ops repo is registered as an ArgoCD application.
4. `status-poller` updates Postgres as state changes. The CLI's `strata cluster list` shows the cluster transitioning to `READY`.
5. The customer's EKS cluster is now self-managing via ArgoCD.

### The co-pilot

The co-pilot is a streaming chat interface. In the CLI it's `strata chat`. In the web UI it's a right-rail on `lg:`, full-page on mobile-web. The copilot is a LangGraph agent with tools:

| Tool | Confirmation required |
|---|---|
| `list_clusters` | no |
| `get_cluster_status` | no |
| `get_cluster_logs` | no |
| `provision_cluster` | **yes** (allow once / always allow / deny) |
| `delete_cluster` | **yes** (allow once / always allow / deny) |
| `retrieve_docs` | no (RAG — calls `retriever-service` for grounded answers) |

All LLM calls go through LiteLLM. Default provider is AWS Bedrock. OpenAI, Anthropic-direct, and Ollama are all swappable via a `ConfigMap` with no code change.

---

## Build Phases (current backlog)

| # | Phase | What ships |
|---|---|---|
| 0 | Delete dead code | ✅ done |
| 1 | Rename to Strata | ✅ done |
| 2 | **Agent sandbox in Kind** — Phase 2 is next | LangGraph + 5 mocked tools + pytest, agent and LiteLLM deployed as k8s manifests to a local Kind cluster |
| 3 | Smallest real backend | Go orchestrator, Postgres in Docker, real HTTP tools |
| 4 | RAG end-to-end | `retriever-service`, `rag-indexer`, Qdrant, `retrieve_docs` tool |
| 5 | Real EKS + bootstrap cluster + Next.js + CLI | `terraform/aws/` actually runs; CLI is the primary interface |
| 6 | SaaS layer | Zitadel, CFN onboarding, cross-account IAM, Kong, Argo Workflows, External Secrets, PLG |
| 7+ | Mobile (Expo) | deferred |

The full plan with effort estimates, deliverables, and "definition of done" is in `AGENTS.md §4` and `handoff.md`. **If you're new to a session, read `handoff.md` first** — it has the live state and the "next session" notes.

---

## Tech Stack (locked)

| Layer | Choice | Lands in |
|---|---|---|
| Agent runtime | LangGraph + LangChain (Python) | Phase 2 |
| Model proxy | LiteLLM | Phase 2 |
| Backend services | Go (chi, sqlx, zerolog) | Phase 3+ |
| Database | CloudNativePG (Postgres operator) | Phase 5+ |
| Vector store (RAG) | Qdrant | Phase 4 (Docker) → 5+ (k8s) |
| Embedding model (RAG) | Bedrock Titan Embeddings v2 via LiteLLM | Phase 4 |
| IaC for customer clusters | Terraform in a Go subprocess | Phase 5+ |
| Control plane cluster | Strata-prod EKS | Phase 5+ |
| Orchestration | Argo Workflows | Phase 6+ |
| Auth | Zitadel (OIDC) | Phase 6+ |
| Ingress | Kong | Phase 6+ |
| Secrets | External Secrets Operator → AWS Secrets Manager | Phase 6+ |
| Observability | Prometheus + Grafana + Loki + Tempo | Phase 6+ |
| Web frontend | Next.js 15 (App Router) | Phase 5+ |
| Primary interface | Python CLI (Typer) | Phase 5+ |
| Mobile frontend | Expo + Expo Router | Phase 7+ (deferred) |
| Languages | Go (services), Python (agent + CLI), TypeScript (web) | |

---

## API Surface (frozen)

| Method | Path | Service | Purpose |
|---|---|---|---|
| `POST` | `/clusters` | orchestrator | Provision a new cluster |
| `GET` | `/clusters` | orchestrator | List user's clusters |
| `GET` | `/clusters/{id}` | orchestrator | Fast status poll |
| `DELETE` | `/clusters/{id}` | orchestrator | Deprovision |
| `GET` | `/dashboard/summary` | orchestrator | Aggregate counts by status |
| `POST` | `/agent/chat` | agent-service | Streamed chat with the co-pilot |
| `PUT` | `/users/me/github-token` | orchestrator | Persist GitHub token |

Internal (not exposed externally):
- `PATCH /internal/clusters/{id}/status` — called by the orchestrator goroutine (Phase 5) or Argo Workflows (Phase 6+).
- `POST /internal/onboarding/verify` — STS assume-role verification. **Phase 6 only.**
- `POST /retrieve`, `POST /index`, `DELETE /index/{collection}/{id}` — `retriever-service`. Internal ClusterIP, called only by `agent-service` and `rag-indexer`.

---

## Local Development (today)

The only runnable piece today is the `sample-app/` — a Go microservices app that is the deployment target for Strata-provisioned clusters. It is **not** the Strata platform; it is a sample app with its own docker-compose, kind config, and Tiltfile.

```bash
# Local sample app dev
docker-compose -f sample-app/docker-compose.yml up

# Kind cluster + Tiltfile dev
kind create cluster
cd sample-app && tilt up
```

Phase 2 ships a working LangGraph agent and a LiteLLM proxy, both running as k8s Deployments in a local Kind cluster. The dev loop is `make kind-up && make build && make apply && make chat`. No docker-compose for the platform.

---

## Documentation

- [AGENTS.md](./AGENTS.md) — full plan, locked decisions, phases, "what's coming"
- [handoff.md](./handoff.md) — live state across sessions (read this first in a new session)
- [specs/strata_master_doc.md](./specs/strata_master_doc.md) — design document
- [specs/sample_app_architecture.md](./specs/sample_app_architecture.md) — sample app architecture
- [sample-app/AGENTS.md](./sample-app/AGENTS.md) — Go service lint rules for the sample app
