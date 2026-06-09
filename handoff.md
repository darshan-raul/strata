# Handoff

> **Live state across sessions.** Update this at the end of every working session.
> AGENTS.md is the source of truth for the plan; this file is the source of truth for *where we are right now*.

---

## Current Session

**Date:** 2026-06-09
**Agent session:** Session 2 — RAG addition
**Focus:** decided on RAG, updated AGENTS.md and handoff.md to reflect it

---

## Decisions Locked

### From Session 1 (still in force)

| Question | Decision |
|---|---|
| Frontend stack | **TanStack Start (web) + Expo/RN (mobile)** — drops Flutter entirely |
| Mobile scope | **Defer detailed scope** — ship scaffold with placeholder screens |
| Naming | **Rename everything to Strata now** — drop "Accio" and "Observatory" entirely |
| Scope of work | **Full rewrite plan documented** — frontend + backend unblockers |
| AWS access flow | **Cross-account IAM role only** — no popup OIDC, no access keys |
| Co-pilot scope | **Full agent with all tools** — application-level confirmation UX |
| Control plane cluster | **Strata-prod EKS** in our AWS account |
| Postgres | **CloudNativePG** operator in-cluster |
| Customer cluster IaC | **Terraform in a Go subprocess** (v1); Crossplane deferred |
| Auth | **Zitadel** self-hosted in-cluster (replaces Cognito) |
| Agent runtime | **agent-service in Python** (FastAPI + LangGraph + LangChain) |
| Model abstraction | **LiteLLM proxy** sidecar |
| Orchestration | **Argo Workflows** (replaces Step Functions) |
| Ingress | **Kong** (reuses sample-app dependency) |
| Secrets | **External Secrets Operator → AWS Secrets Manager** |
| Observability | **PLG stack** in-cluster (Prometheus, Grafana, Loki, Tempo) |

### From Session 2 (new — RAG)

| Question | Decision |
|---|---|
| RAG scope (v1) | **Platform data + Strata's own `docs/`** (Flavors A + B). Logs/incidents (Flavor C) deferred. |
| Embedding model | **Bedrock Titan Embeddings v2** via LiteLLM (`bedrock/amazon.titan-embed-text-v2:0`, 1024-dim) |
| Vector store | **Qdrant** sidecar (single replica, 20Gi PVC, S3 snapshot backup) |
| Docs source | **Strata's own `docs/` directory** — plus curated excerpts of ArgoCD / EKS / AWS troubleshooting |
| RAG ingestion | **Periodic pull** via `rag-indexer` Go service (60s cadence) for v1; event-driven deferred |
| Reranking | **None** for v1 — add only if measured recall is low |
| Retriever auth | **API key** in k8s Secret, internal ClusterIP service |
| RAG access pattern | **All retrieval goes through `retriever-service`**. Only `retriever-service` and `rag-indexer` may talk to Qdrant directly. |

---

## Phase Status

- [x] **Documentation**
  - [x] AGENTS.md rewritten with full plan (12 sections + RAG §6.5)
  - [x] handoff.md created and being maintained
  - [x] README.md rewritten from scratch (architecture, status, API, how-it-works, stack)
- [x] **Phase 0 — Delete dead code** ✅
  - Deleted: `flutter_app/`, `mobileviews/`, `sampleclientapp/`, `infra_diagram.html`, `infra/`, `lambdas/`, `buildspec.yml`, `onboarding_cfn.yaml`
  - Created: `onboarding/strata-platform-role.yaml` (cross-account role moved here, `AdministratorAccess` scoped down to explicit `eks:*`/`ec2:*`/narrow `iam:*`)
  - Created: `onboarding/README.md`
- [x] **Phase 1 — Rename to Strata** ✅
  - Renamed: `sample-app/helm/accio-chart/` → `sample-app/helm/strata-chart/`
  - Renamed: `sample-app/accio-kind.yaml` → `sample-app/strata-kind.yaml`
  - Renamed: `specs/accio_master_doc.md` → `specs/strata_master_doc.md`
  - Updated: `Chart.yaml` name `strata-chart`; `name: strata-portal-ui` in `package.json`
  - Updated: helm helpers (`accio.*` → `strata.*`)
  - Updated: 5× `go.mod` (`github.com/accio/X` → `github.com/strata/X`)
  - Updated: 5× `main.go` DSN strings + 5× `k8s/base/services/*.yaml` DSN strings
  - Updated: `Tiltfile`, `index.html`, `auth-api.js`, CI workflows (path filter fixed, ECR prefix, names), `sample-app/AGENTS.md`, `specs/strata_master_doc.md`
  - Verification: clean
- [x] **RAG plan** ✅ (Session 2)
  - Qdrant chosen as vector store (over pgvector)
  - Bedrock Titan v2 via LiteLLM chosen as embedding model
  - Platform data + Strata docs in scope for v1
  - `retriever-service` and `rag-indexer` Go services added to Phase 4 plan
  - `retrieve_docs` LangChain tool added to Phase 6 plan
  - Qdrant subchart added to Phase 3 plan
  - Cross-cutting rule added: RAG goes through retriever-service
- [ ] **Phase 2 — Bootstrap control-plane EKS** — next session
- [ ] **Phase 3 — Helm umbrella chart** — pending (now includes Qdrant)
- [ ] **Phase 4 — Go services** — pending (now includes retriever-service + rag-indexer)
- [ ] **Phase 5 — Argo Workflow templates** — pending
- [ ] **Phase 6 — `agent-service` (LangGraph + LangChain + LiteLLM)** — pending (now includes `retrieve_docs` tool)
- [ ] **Phase 7 — `web/` (TanStack Start)** — pending
- [ ] **Phase 8 — `mobile/` (Expo)** — pending
- [ ] **Phase 9 — End-to-end verification** — pending
- [ ] **Phase 10 — Polish + CI hardening** — pending

---

## API Surface (frozen, for the rewrite)

| Method | Path | Owner service | Purpose |
|---|---|---|---|
| POST | `/clusters` | orchestrator | Provision a new cluster. Kicks Argo Workflow. |
| GET | `/clusters` | orchestrator | List user's clusters. |
| GET | `/clusters/{id}` | orchestrator | Fast status poll. |
| DELETE | `/clusters/{id}` | orchestrator | Deprovision. Kills Argo Workflow if running, then runs `deprovision-cluster`. |
| GET | `/dashboard/summary` | orchestrator | Aggregate counts by status. |
| POST | `/agent/chat` | agent-service | Streamed chat with the Co-Pilot (SSE). |
| PUT | `/users/me/github-token` | orchestrator | Persist GitHub token (used for ops-repo access). |

Internal (not exposed via Kong):
- `PATCH /internal/clusters/{id}/status` — called by Argo Workflows
- `POST /internal/onboarding/verify` — STS assume-role verification

`retriever-service` is internal-only (ClusterIP, not Kong-exposed):
- `POST /retrieve` — embed + vector search + return chunks
- `POST /index` — embed + upsert
- `DELETE /index/{collection}/{id}` — delete chunk
- `GET /healthz` — readiness/liveness

---

## Target Repo Layout (post-Phase 1, with RAG in mind)

```
strata/
├── AGENTS.md                # updated with RAG
├── handoff.md               # this file
├── README.md                # rewritten
├── onboarding/              # extracted from onboarding_cfn.yaml
│   ├── README.md
│   ├── strata-platform-role.yaml
│   └── policies/
├── .github/workflows/       # updated — path filter fixed
├── sample-app/              # renamed/cleaned
│   ├── helm/strata-chart/
│   ├── strata-kind.yaml
│   ├── services/*/go.mod    # github.com/strata/X
│   ├── services/portal-ui/  # name: strata-portal-ui
│   └── ...
├── specs/strata_master_doc.md
├── specs/sample_app_architecture.md
├── specs/archives/          # historical, untouched
├── diagrams/                # stale PNGs; rewrite in Phase 7/9
├── terraform/aws/           # UNCHANGED — customer-side EKS module
├── .gitignore
└── (Phase 2+ folders not yet created)
    # control-plane/
    #   bootstrap/                          # Phase 2
    #   helm/strata/
    #     templates/
    #       qdrant/                         # NEW (Phase 3)
    #       retriever-service-deployment.yaml  # NEW (Phase 4)
    #       rag-indexer-deployment.yaml     # NEW (Phase 4)
    #   argocd-apps/
    # services/
    #   shared/                             # Go module
    #   orchestrator/                       # Go
    #   provisioner-worker/                 # Go
    #   status-poller/                      # Go
    #   argocd-sync/                        # Go
    #   health-monitor/                     # Go
    #   retriever-service/                  # Go (NEW)
    #   rag-indexer/                        # Go (NEW)
    #   agent-service/                      # Python
    # workflows/
    #   provision-cluster.yaml              # Phase 5
    #   deprovision-cluster.yaml
    #   reindex-docs.yaml                   # NEW (Phase 4+)
    #   lib/
    # docs/                                 # NEW (Phase 7+)
    #   argo-cd/
    #   eks/
    #   strata/
    # web/                                  # Phase 7
    # mobile/                               # Phase 8
```

---

## Open Questions / Blockers

None. All locked decisions are recorded in AGENTS.md §3 and §6.5.

---

## Notes for the Next Session

### Phase 2 (next) — `control-plane/bootstrap/`

Goal: one-time Terraform that creates the **Strata-prod EKS** cluster.

Files to create:
- `control-plane/bootstrap/main.tf` — VPC (3 AZs, public + private subnets, NAT), EKS 1.29+ with managed node group, S3 bucket for TF state + DynamoDB lock table, KMS key, ACM cert
- `control-plane/bootstrap/variables.tf`
- `control-plane/bootstrap/outputs.tf` — cluster name, endpoint, kubeconfig command, IRSA role ARNs
- `control-plane/bootstrap/providers.tf`
- `control-plane/bootstrap/README.md`

Decisions already made in AGENTS.md §3:
- VPC: 3 AZs, public + private subnets, NAT
- EKS: 1.29+ managed node group
- State: S3 + DynamoDB lock
- Encryption: KMS
- IRSA roles for major workloads (LiteLLM, External Secrets, Argo). **RAG note:** add an IRSA role for `retriever-service` and `rag-indexer` if they need AWS access; they may not — Qdrant is in-cluster and embeddings go through LiteLLM. Add only if needed.

### Carryover gotchas

- **`onboarding/strata-platform-role.yaml`** uses `StrataProvisionerRoleName` and `StrataReaderRoleName` parameters. Defaults are `strata-provisioner-worker` and `strata-status-poller` — these are the IRSA role names the bootstrap Terraform will create. Update the defaults if you pick different names.
- **The diagrams in `diagrams/`** are stale (depict the old serverless architecture). The README no longer references them. Don't delete them — they're not in the dead-code list; rewriting is a Phase 7/9 task.
- **CI workflow path filters** are correct (`sample-app/services/*-service/**`). Until new `web/`, `mobile/`, and `services/` directories are created, the existing two CI workflows cover what we have.
- **Sample app's `auth-service`** (in `sample-app/services/auth-service/`) was NOT deleted in Phase 0. It's a sample-app-internal auth using Dex and a hardcoded JWT secret. It's separate from the Strata control plane's Zitadel auth. Leave it for now; clean up when `web/` is built (the new `web/` replaces `portal-ui` which currently uses this auth).
- **RAG prerequisites for Phase 3:** the LiteLLM config map in `control-plane/helm/strata/values.yaml` must enable `bedrock/amazon.titan-embed-text-v2:0` as an embedding model, not just chat. IRSA for the LiteLLM pod needs `bedrock:InvokeModel` for the embedding model ARN. Flag this in the bootstrap IAM planning.
- **Qdrant in Phase 3:** single replica, 20Gi PVC, S3 snapshot CronJob. Disable anonymous access; create an API key Secret and wire it into `retriever-service` and `rag-indexer`.
- **`docs/` directory for Phase 7+:** when you create it, structure it as `docs/{argo-cd,eks,strata}/` with markdown files. Initial set: 1 architecture doc, 1 onboarding doc, 1-2 ArgoCD troubleshooting excerpts. Don't over-invest; the rag-indexer workflow will pick it up.

---

## Session Log

### 2026-06-09 — Session 1
- User asked for full project evaluation.
- Identified Flutter app as dead weight; recommended TanStack Start + Expo.
- Discussed K8s-native control plane, dropping Lambda/Step Functions.
- Locked all architecture decisions.
- Wrote AGENTS.md (full plan, 12 sections, ~20KB).
- Wrote handoff.md.
- Rewrote README.md from scratch.
- Phase 0: deleted 8 dead code targets via `git rm`. Extracted `onboarding_cfn.yaml` to `onboarding/strata-platform-role.yaml` and scoped down `AdministratorAccess`. Created `onboarding/README.md`.
- Phase 1: renamed 3 files/dirs, updated ~25 files for Strata branding. Verified clean via grep.

### 2026-06-09 — Session 2
- User asked about adding RAG.
- Analyzed RAG options (vector store, embedding model, scope, ingestion pattern).
- User chose: Qdrant + Bedrock Titan v2 + platform data + own docs.
- Updated AGENTS.md:
  - Architecture diagram (added `retriever-service`, `rag-indexer`, Qdrant)
  - Locked decisions table (added 6 RAG rows)
  - Cross-cutting rules (added 2 RAG rules)
  - New section §6.5 (RAG overview, components, scope, cross-cutting rule)
  - Phase 3 (added Qdrant to Helm chart)
  - Phase 4 (added `retriever-service`, `rag-indexer`; updated `shared/` Go module description)
  - Phase 6 (added `retrieve_docs` tool)
  - Phase status: 0 and 1 marked DONE
- Updated handoff.md (this file):
  - Locked decisions table (added RAG section)
  - Phase status (added RAG plan complete)
  - Target repo layout (added RAG components and `docs/` directory)
  - Notes for next session (added RAG gotchas for Phase 3/4/7)

**Carryover to next session:**
- Start Phase 2: `control-plane/bootstrap/`.
- If user wants a different node group size, VPC CIDR, or EKS version, confirm before writing `main.tf`.
- Remember: when Phase 3 lands, the LiteLLM config must enable Bedrock Titan v2 as an *embedding* model, not just chat. IRSA for LiteLLM needs `bedrock:InvokeModel` for the embedding model.
- When Phase 3 lands, add a Qdrant subchart with API key auth, 20Gi PVC, S3 snapshot CronJob.
- Update this handoff with phase-complete status when Phase 2 lands.
