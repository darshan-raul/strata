# Strata

Strata provisions production-grade EKS clusters in your AWS account via GitOps and a Kubernetes-native control plane. Connect a GitHub ops repo and an AWS account; Strata creates an EKS cluster in that account, installs ArgoCD, and syncs the cluster from your ops repo. A built-in AI Co-Pilot lets you drive the platform conversationally.


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
                 │   └─ agent-service (Python: FastAPI +         │
                 │       LangGraph + LangChain) ──► LiteLLM     │
                 │                          └─► Bedrock/OpenAI/ │
                 │                              Anthropic/Ollama│
                 │                                              │
                 │ Argo Workflows (replaces Step Functions)     │
                 │ CloudNativePG (Postgres)                     │
                 │ Redis (in-flight state)                      │
                 │ Zitadel (OIDC)                               │
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

## Repository Layout

```
strata/
├── AGENTS.md            # source of truth for the plan
├── handoff.md           # live state across sessions
├── README.md            # this file
├── control-plane/       # Helm chart + bootstrap Terraform for Strata-prod
├── services/            # Go and Python control-plane services
├── workflows/           # Argo Workflow templates
├── terraform/aws/       # customer-side EKS module
├── onboarding/          # CloudFormation template customers deploy
├── web/                 # TanStack Start (web frontend)
├── mobile/              # Expo (mobile frontend)
├── sample-app/          # sample target app deployed to customer clusters
├── diagrams/            # architecture diagrams
├── specs/               # design documents
├── .github/workflows/   # CI
└── docs/                # architecture, API, tool reference
```

---

## How It Works

### Onboarding
1. User signs up via the web or mobile app. Auth is handled by Zitadel (OIDC).
2. User pastes their GitHub personal access token. Stored encrypted in Postgres.
3. User downloads the onboarding CloudFormation template and deploys it to their AWS account. This creates a cross-account IAM role (`strata-platform-provisioner`) with an external ID generated per-user.
4. User pastes the role ARN back into Strata. Strata verifies via `sts:AssumeRole`.
5. User pastes the URL of their ops repo (a Git repo containing Kubernetes manifests).

### Provisioning a cluster
1. User clicks "Provision cluster" in the web app, fills out a form (name, region, instance type, k8s version).
2. `orchestrator-service` writes a row to the `clusters` table in Postgres (status: `INITIATED`) and kicks off an Argo Workflow.
3. The workflow assumes the cross-account role, runs Terraform (`terraform/aws/` module) in the customer's account, waits for EKS to be `ACTIVE`, then registers the user's ops repo with the cluster's ArgoCD.
4. `status-poller` updates Postgres as state changes. The web app polls `/clusters/{id}` until status is `READY` or `FAILED`.
5. The customer's EKS cluster is now self-managing via ArgoCD. Future changes to their ops repo sync automatically.

### Co-Pilot
The right-rail co-pilot (full-page on mobile-web and in the Expo app) is a streaming chat interface backed by a LangGraph agent. It can call five tools:

| Tool | Confirmation required |
|---|---|
| `list_clusters` | no |
| `get_cluster_status` | no |
| `get_cluster_logs` | no |
| `provision_cluster` | **yes** (allow once / always allow / deny) |
| `delete_cluster` | **yes** (allow once / always allow / deny) |

All LLM calls go through LiteLLM. The default provider is AWS Bedrock. OpenAI, Anthropic-direct, and Ollama are configured via a `ConfigMap` without code changes.

### Deprovisioning
User triggers delete from the web app. `orchestrator-service` runs the `deprovision-cluster` Argo Workflow, which `terraform destroy`s the customer-side resources and removes the cluster row.

---

## Tech Stack (locked)

| Layer | Choice |
|---|---|
| Control plane | Strata-prod EKS (in our AWS account) |
| Orchestration | Argo Workflows |
| Database | CloudNativePG (Postgres operator) |
| Cache | Redis |
| Auth | Zitadel (OIDC) |
| Ingress | Kong |
| Secrets | External Secrets Operator → AWS Secrets Manager |
| Observability | Prometheus + Grafana + Loki + Tempo |
| Service mesh | (none for v1; Kong handles north-south) |
| IaC for customer clusters | Terraform in a Go subprocess |
| Model proxy | LiteLLM |
| Agent framework | LangGraph + LangChain (Python) |
| Web frontend | TanStack Start (TypeScript, Vite) |
| Mobile frontend | Expo + Expo Router (React Native) |
| Programming languages | Go (services), Python (agent), TypeScript (frontend) |

---

## API Surface (frozen)

| Method | Path | Service | Purpose |
|---|---|---|---|
| `POST` | `/clusters` | orchestrator | Provision a new cluster |
| `GET` | `/clusters` | orchestrator | List user's clusters |
| `GET` | `/clusters/{id}` | orchestrator | Fast status poll |
| `DELETE` | `/clusters/{id}` | orchestrator | Deprovision |
| `GET` | `/dashboard/summary` | orchestrator | Aggregate counts by status |
| `POST` | `/agent/chat` | agent-service | Streamed chat (SSE) |
| `PUT` | `/users/me/github-token` | orchestrator | Persist GitHub token |

---

## Local Development (today)

The `sample-app/` is a sample Go microservices app that is the deployment target for Strata-provisioned clusters. Until the rewrite is complete, this is the only runnable piece.

```bash
# Local sample app dev
docker-compose -f sample-app/docker-compose.yml up

# Kind cluster + Tiltfile dev
kind create cluster
cd sample-app && tilt up
```

---

## Documentation

- [AGENTS.md](./AGENTS.md) — full plan, locked decisions, phases
- [handoff.md](./handoff.md) — live state, session log
- [specs/strata_master_doc.md](./specs/strata_master_doc.md) — design document (rewriting during Phase 1)
- [specs/sample_app_architecture.md](./specs/sample_app_architecture.md) — sample app architecture
- [sample-app/AGENTS.md](./sample-app/AGENTS.md) — Go service lint rules

