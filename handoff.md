# Handoff

> **Live state across sessions.** Update this at the end of every working session.
> AGENTS.md is the source of truth for the plan; this file is the source of truth for *where we are right now*.

---

## Current Session

**Date:** 2026-06-10
**Agent session:** Session 3 — major re-plan (agent-first, single-user, Next.js + CLI)
**Focus:** realigned the build order around the user's actual goals (learn LangGraph/RAG deeply) and constraints (evenings/weekends, no frontend chops). Re-numbered phases. Updated AGENTS.md.

---

## Decisions Locked

### From Sessions 1–2 (still in force, with changes noted)

| Question | Decision | Notes |
|---|---|---|
| Control plane cluster | **Strata-prod EKS** in our AWS account | lands in Phase 5 |
| Postgres | **CloudNativePG** operator in-cluster | lands in Phase 5/6 |
| Customer cluster IaC | **Terraform in a Go subprocess** (v1); Crossplane deferred | unchanged |
| Agent runtime | **agent-service in Python** (FastAPI + LangGraph + LangChain) | **moved to Phase 2 — first thing built** |
| Model abstraction | **LiteLLM** proxy sidecar | unchanged |
| Orchestration | **Argo Workflows** (replaces Step Functions) | lands in Phase 6 |
| Auth | **Zitadel** self-hosted in-cluster (replaces Cognito) | **Phase 6 only** (single-user in Phases 2–5 uses `MOCK_USER` header) |
| Ingress | **Kong** | **Phase 6 only** (Phase 5 exposes the orchestrator directly) |
| Secrets | **External Secrets Operator → AWS Secrets Manager** | **Phase 6 only** (Phase 5 puts secrets in `.env` / k8s Secret literals) |
| Observability | **PLG stack** in-cluster (Prometheus, Grafana, Loki, Tempo) | **Phase 6 only** |
| Vector store (RAG) | **Qdrant** | Phase 4 (Docker) → Phase 5/6 (k8s) |
| Embedding model | **Bedrock Titan Embeddings v2** via LiteLLM | unchanged |
| RAG scope (v1) | **Platform data + Strata's own `docs/`** | unchanged |
| RAG ingestion | **Periodic pull** via `rag-indexer` Go service (60s cadence) | unchanged |
| Reranking | **None** for v1 | unchanged |
| Retriever auth | **API key** in k8s Secret | Phase 4: `.env`; Phase 5+: k8s Secret |
| RAG access pattern | **All retrieval goes through `retriever-service`** | unchanged |

### From Session 3 (new)

| Question | Decision | Why |
|---|---|---|
| Build order | **Agent first, infrastructure second.** Phase 2 = working LangGraph agent against mocked tools. Real EKS/AWS in Phase 5. | User wants to *learn* LangGraph and RAG deeply. The agent loop is the subject; AWS is the carrier. Building infra first delays the actual learning by months. |
| Initial scope | **Single-user, single-cluster, single AWS account (yours).** Multi-tenant SaaS deferred to Phase 6. | Evenings/weekends budget. Real multi-tenant SaaS is 3–5× the work. |
| Primary interface | **Python CLI (Typer)** — `strata cluster list`, `strata cluster create`, `strata chat`. Web UI is for demos only. | CLI is a native fit for a k8s/AWS user. Bypasses frontend debugging. |
| Web frontend | **Next.js 15 (App Router).** Replaces TanStack Start. | User said TanStack is unfathomable. Next.js is debuggable. |
| Mobile frontend | **Deferred.** Expo scaffolded in a later phase if/when web+CLI+API are stable. | Mobile is the highest-effort, lowest-learning surface for an agentic-AI project. |
| Doc ownership | **Comprehensive AI-authored, user-reviewed.** `docs/` contains full reference docs for langchain, langgraph, litellm, rag, bedrock, nextjs, plus the project-specific agent-architecture. The user reviews and edits; the AI writes the first draft. | The user wanted comprehensive coverage of the entire stack upfront, rather than learning-by-writing. The user remains the editor; future edits go through their review. |
| AWS access flow (Phase 5) | **Direct creds in `.env`** (single-user, your own AWS account). No STS, no external ID. | Phases 2–4 are docker-only. Phase 5 is single-user. Cross-account role model lands in Phase 6. |
| AWS access flow (Phase 6) | **Cross-account IAM role only** (CFN onboarding wizard). | No creds in browser; the existing `strata-platform-provisioner` model. |
| Argo Workflows in Phase 5 | **No.** Phase 5 uses a Go orchestrator-triggered goroutine to drive provision/deprovision. Argo Workflows land in Phase 6. | Cuts a huge piece of Phase 5. The goroutine is fine for one user. |
| Confirmation UX | **Mutation tools still require user confirmation**, but the gate is "always allow" until the web UI's `<ToolCallCard />` lands in Phase 6. | Defer the UI work until we actually have multi-user. |

### Deprecated / changed

- ~~TanStack Start (web) + Expo (mobile)~~ → **Next.js 15 (web) + Expo (deferred) + Typer CLI (primary)**
- ~~10 phases, build infra first, agent last~~ → **6 phases, build agent first, infra second**
- ~~Multi-tenant SaaS from day 1 (Zitadel, CFN, quotas)~~ → **Single-user first, multi-tenant in Phase 6**
- ~~Phase 2 = bootstrap Strata-prod EKS~~ → **Phase 2 = agent sandbox; bootstrap EKS is Phase 5**

---

## Phase Status (re-numbered)

- [x] **Documentation**
  - [x] AGENTS.md rewritten (Sessions 1, 2, 3)
  - [x] handoff.md created and being maintained
  - [x] README.md (rewritten in Session 3 to match new positioning)
- [x] **Phase 0 — Delete dead code** ✅
  - Deleted: `flutter_app/`, `mobileviews/`, `sampleclientapp/`, `infra_diagram.html`, `infra/`, `lambdas/`, `buildspec.yml`, `onboarding_cfn.yaml`
  - Created: `onboarding/strata-platform-role.yaml` (cross-account role moved here, `AdministratorAccess` scoped down to explicit `eks:*`/`ec2:*`/narrow `iam:*`)
  - Created: `onboarding/README.md`
- [x] **Phase 1 — Rename to Strata** ✅
  - Renamed: `sample-app/helm/accio-chart/` → `sample-app/helm/strata-chart/`
  - Renamed: `sample-app/accio-kind.yaml` → `sample-app/strata-kind.yaml`
  - Renamed: `specs/accio_master_doc.md` → `specs/strata_master_doc.md`
  - Updated: `Chart.yaml`, `package.json`, helm helpers, 5× `go.mod`, 5× `main.go` DSN strings, 5× k8s DSN strings, `Tiltfile`, `index.html`, `auth-api.js`, CI workflows, `sample-app/AGENTS.md`, `specs/strata_master_doc.md`
  - Verification: clean
- [x] **RAG plan** ✅ (Session 2)
  - Qdrant chosen as vector store (over pgvector)
  - Bedrock Titan v2 via LiteLLM chosen as embedding model
  - Platform data + Strata docs in scope for v1
  - `retriever-service` and `rag-indexer` Go services added to Phase 4 plan
  - `retrieve_docs` LangChain tool wired into Phase 4 (moved from Phase 6)
  - Cross-cutting rule: RAG goes through `retriever-service`
- [x] **Session 3 re-plan** ✅
  - Agent-first ordering, single-user scope, Next.js + CLI, evenings/weekends cadence
  - AGENTS.md re-numbered to 6 phases; §3, §4, §6.5, §7, §8, §9, §10, §11 updated
  - handoff.md updated (this file)
  - README.md rewritten to match new positioning
- [ ] **Phase 2 — Agent sandbox** — **NEXT**
  - `services/agent-service/` (Python, FastAPI, LangGraph, LangChain, LiteLLM)
  - 5 mocked tools, NDJSON streaming, pytest
  - `docs/langgraph-tools.md` (superseded in Session 5 by `docs/langgraph.md`)
  - `docs/strata/agent-architecture.md`
- [ ] **Phase 3 — Smallest real backend** — pending
- [ ] **Phase 4 — RAG end-to-end** — pending
- [ ] **Phase 5 — Real EKS + bootstrap cluster + Next.js + CLI** — pending
- [ ] **Phase 6 — SaaS layer (Zitadel, CFN, Kong, Argo, ESO, PLG)** — pending
- [ ] **Phase 7+ — Mobile (Expo)** — pending (deferred)

---

## API Surface (frozen, for the rewrite)

| Method | Path | Owner service | Purpose |
|---|---|---|---|
| POST | `/clusters` | orchestrator | Provision a new cluster. Kicks Argo Workflow (Phase 6+; Phase 5 uses a goroutine). |
| GET | `/clusters` | orchestrator | List user's clusters. |
| GET | `/clusters/{id}` | orchestrator | Fast status poll. |
| DELETE | `/clusters/{id}` | orchestrator | Deprovision. Kills Argo Workflow if running, then runs `deprovision-cluster`. |
| GET | `/dashboard/summary` | orchestrator | Aggregate counts by status. |
| POST | `/agent/chat` | agent-service | Streamed chat with the Co-Pilot. NDJSON in Phase 2–4, SSE in Phase 5+ when the web UI needs it. |
| PUT | `/users/me/github-token` | orchestrator | Persist GitHub token (used for ops-repo access). |

Internal (not exposed via Kong):
- `PATCH /internal/clusters/{id}/status` — called by Argo Workflows (Phase 6+) or the orchestrator's goroutine (Phase 5) to update status.
- `POST /internal/onboarding/verify` — STS assume-role verification helper. **Phase 6 only** (single-user in Phase 5, no cross-account role).
- `POST /retrieve`, `POST /index`, `DELETE /index/{collection}/{id}` — `retriever-service`. Internal ClusterIP, called only by `agent-service` and `rag-indexer`.

---

## Target Repo Layout (post-Phase 1, post-Session 3 re-plan)

```
strata/
├── AGENTS.md                # source of truth (Sessions 1–3)
├── handoff.md               # this file
├── README.md                # rewritten in Session 3
├── onboarding/              # extracted from onboarding_cfn.yaml
│   ├── README.md
│   ├── strata-platform-role.yaml
│   └── policies/
├── .github/workflows/       # path filters fixed in Phase 1
├── sample-app/              # renamed/cleaned, runs locally
│   ├── helm/strata-chart/
│   ├── strata-kind.yaml
│   ├── services/*/go.mod    # github.com/strata/X
│   └── ...
├── specs/
│   ├── strata_master_doc.md
│   ├── sample_app_architecture.md
│   └── archives/            # historical, untouched
├── diagrams/                # stale PNGs; rewrite later
├── terraform/aws/           # UNCHANGED — customer-side EKS module
├── docs/                    # NEW (Phase 4+) — comprehensive AI-authored, user-reviewed
│   ├── langchain.md
│   ├── langgraph.md
│   ├── litellm.md
│   ├── bedrock.md
│   ├── rag.md
│   ├── nextjs.md
│   ├── strata/
│   │   ├── agent-architecture.md
│   │   └── control-plane.md         # Phase 5+
│   ├── argo-cd/                     # Phase 4+ curated excerpts
│   └── eks/                         # Phase 4+ curated excerpts
├── services/                # NEW (Phase 2+)
│   ├── shared/              # Go module
│   ├── orchestrator/        # Go (Phase 3+)
│   ├── provisioner-worker/  # Go (Phase 5+)
│   ├── status-poller/       # Go (Phase 5+)
│   ├── argocd-sync/         # Go (Phase 5+)
│   ├── health-monitor/      # Go (Phase 5+)
│   ├── retriever-service/   # Go (Phase 4+)
│   ├── rag-indexer/         # Go (Phase 4+)
│   └── agent-service/       # Python (Phase 2+)
├── cli/                     # NEW (Phase 5) — Typer, primary interface
├── web/                     # NEW (Phase 5) — Next.js 15, demo interface
├── control-plane/           # NEW (Phase 5+)
│   ├── bootstrap/           # Terraform for Strata-prod EKS
│   ├── helm/strata/         # Umbrella Helm chart (Phase 6+)
│   └── argocd-apps/
├── workflows/               # Argo Workflow templates (Phase 6+)
│   ├── provision-cluster.yaml
│   ├── deprovision-cluster.yaml
│   └── lib/
├── docker-compose.yml       # NEW (Phase 3+) at repo root
└── .gitignore
```

---

## Open Questions / Blockers

None. All locked decisions are recorded in AGENTS.md §3.

---

## Notes for the Next Session

### Phase 2 (next) — Agent sandbox in Kind (`services/agent-service/` + k8s manifests)

**Goal:** a working LangGraph agent you can talk to, that calls mocked tools, that you fully understand. **Everything runs in a local Kind cluster from day one.** No docker-compose, no EKS, no auth. Just k8s manifests, kind, kubectl port-forward, and curl.

**Repo layout to create:**

```
strata/
├── strata-dev-kind.yaml                 # Kind cluster config (port mappings, registry)
├── Makefile                             # kind-up / build / apply / chat / logs / kind-down
├── control-plane/
│   └── manifests/                       # raw k8s manifests, no Helm in Phase 2
│       ├── 00-namespace.yaml
│       ├── 10-litellm/
│       │   ├── deployment.yaml
│       │   ├── service.yaml             # ClusterIP:4000
│       │   ├── configmap.yaml           # model list, AWS region
│       │   └── secret.yaml.example      # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (gitignored)
│       └── 20-agent-service/
│           ├── deployment.yaml
│           └── service.yaml             # NodePort:30800
├── services/agent-service/
│   ├── pyproject.toml                   # uv-managed
│   ├── Dockerfile                       # python:3.12-slim, uv sync, uvicorn
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                      # FastAPI, POST /chat streams NDJSON
│   │   ├── graph.py                     # LangGraph state machine: think → tool_call → respond
│   │   ├── state.py                     # typed state (messages, thread_id)
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   └── litellm_provider.py      # calls http://litellm:4000/v1/chat/completions (in-cluster DNS)
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── list_clusters.py         # @tool, returns Pydantic model
│   │       ├── get_cluster_status.py
│   │       ├── get_cluster_logs.py
│   │       ├── provision_cluster.py
│   │       └── delete_cluster.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_graph.py                # asserts correct tool called for given prompt
│   │   └── test_tools.py                # tool schema/return shape sanity
│   └── README.md                        # how to run, how to add a tool
└── docs/
    ├── langgraph-tools.md               # AI-written; user reviews
    └── strata/
        └── agent-architecture.md        # AI-written; user reviews
```

**Graph (Phase 2, minimal):** three nodes.
1. `think` — calls LiteLLM with the current message history. If the response includes `tool_calls`, route to `tool_call`. Otherwise, route to `respond`.
2. `tool_call` — invokes the named tool (mocked), appends a `ToolMessage` to state, routes back to `think`.
3. `respond` — terminal; emits the assistant's final text to the NDJSON stream.

No checkpointer, no confirmation flow, no RAG node. Pure in-memory state.

**Tools (Phase 2, all mocked):**
- `list_clusters` — returns `[{id, name, status, region, k8s_version}]` (3 hardcoded rows)
- `get_cluster_status(id)` — returns `{id, status, last_updated, ...}` (depends on id)
- `get_cluster_logs(id, since)` — returns `["log line 1", "log line 2", ...]` (hardcoded)
- `provision_cluster(name, region, k8s_version)` — returns `{id, status: "INITIATED"}`
- `delete_cluster(id)` — returns `{id, status: "DELETING"}`

Each is `@tool`-decorated, returns a Pydantic model. Tool descriptions matter — they're what the LLM sees.

**Streaming:** NDJSON, one JSON object per line:
```json
{"type": "token", "text": "..."}
{"type": "tool_call", "name": "list_clusters", "args": {}}
{"type": "tool_result", "name": "list_clusters", "result": [...]}
{"type": "done"}
```

**Tests (pytest) — minimum bar:**
1. Given prompt "list my clusters", the graph calls the `list_clusters` tool.
2. After the tool result, the next LLM call includes the tool result in its message history.
3. The streaming endpoint emits exactly one `{"type": "done"}`.

**Docs to write (the user reviews and edits; AI generates the first draft):**
- `docs/langgraph-tools.md` — explain the state machine, the `messages` reducer, AI vs Tool messages, how `@tool` decoration surfaces as JSON schema to the LLM.
- `docs/strata/agent-architecture.md` — Mermaid diagram of the loop.

**LiteLLM (in-cluster, not on laptop):**
- Deployed as a Deployment in the `strata` namespace, listens on `:4000`.
- Configured with Bedrock models via env vars: `bedrock/amazon.nova-pro-v1:0` (chat) and `bedrock/amazon.titan-embed-text-v2:0` (embed, for Phase 4).
- AWS creds come from a k8s Secret — **not IRSA** because IRSA only works on real EKS, not Kind. `secret.yaml.example` is committed; the real `secret.yaml` is gitignored.

**Dev loop (no docker-compose):**
```bash
make kind-up       # create Kind cluster with port mappings, start local registry
make build         # build agent-service image, push to localhost:5000
make apply         # kubectl apply -f control-plane/manifests/
make chat          # port-forward + curl /chat
make logs-agent    # tail agent-service logs
make kind-down     # delete the dev cluster
```

The same k8s manifests will deploy to EKS in Phase 5 (with IRSA instead of a k8s Secret for AWS creds).

### Carryover gotchas

- **`uv` is the package manager**, not pip. Use `uv sync` and `uv run pytest` inside the agent container for tests; `uv` outside for local iteration.
- **Local registry is required.** Kind can't pull from Docker Hub by default; you build and push to `localhost:5000`. The `strata-dev-kind.yaml` patches `imageRepository` so Kind nodes can pull from the local registry.
- **Do NOT add a checkpointer in Phase 2.** A common LangGraph tutorial trap. The graph holds state in memory for the duration of one HTTP request; that's enough.
- **Do NOT add a confirmation node in Phase 2.** That lands with the web UI in Phase 5/6.
- **Tools MUST be Pydantic models**, not raw dicts. This forces schema generation that the LLM can read.
- **The "what's a chunk?" question is for Phase 4.** Don't pre-optimize for RAG in Phase 2.
- **AWS creds in a k8s Secret are fine for Phase 2/5** but they get rotated to IRSA when you move to EKS in Phase 5. The secret layout should make that swap easy (single `aws-credentials` Secret, mounted as env vars).
- **If you don't have Bedrock access**, swap the LiteLLM model in `configmap.yaml` to `gpt-4o-mini` or `claude-3-haiku-20240307` and put the API key in the secret. The architecture stays the same; only the `model_list` entry changes.

### Definition of done for Phase 2

- [ ] `strata-dev-kind.yaml` provisions a Kind cluster with port mappings `30000` and `30800`.
- [ ] `control-plane/manifests/00-namespace.yaml` creates the `strata` namespace.
- [ ] `control-plane/manifests/10-litellm/` deploys LiteLLM with a Bedrock-backed model list, reachable on `litellm:4000` in-cluster.
- [ ] `control-plane/manifests/20-agent-service/` deploys `agent-service` on `NodePort:30800`.
- [ ] `services/agent-service/` has the layout above; `Dockerfile` builds with `uv`.
- [ ] `make kind-up && make build && make apply` brings the cluster up.
- [ ] `make chat` (or `kubectl port-forward + curl`) reaches the agent and gets NDJSON back including a `tool_call` for `list_clusters` and a final `done`.
- [ ] `uv run pytest` (run inside the agent container) is green for `test_graph.py` and `test_tools.py`.
- [ ] `docs/langgraph-tools.md` exists.
- [ ] `docs/strata/agent-architecture.md` exists with a Mermaid diagram.
- [ ] handoff.md updated with phase-complete status.

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
- Updated AGENTS.md (architecture diagram, locked decisions, cross-cutting rules, §6.5 RAG overview, phase plans, phase status).
- Updated handoff.md (locked decisions, phase status, target repo layout, next-session notes).

### 2026-06-10 — Session 3 (this session)
- User opened with a candid summary of constraints: knows AWS/k8s deeply, knows nothing about LangGraph/LangChain/RAG/Bedrock, can't fathom debugging TanStack. Asked for a re-plan.
- Asked 4 sets of questions, got clear answers:
  - **Goal:** portfolio / demo piece.
  - **Frontend:** Next.js (debuggable) + CLI (primary).
  - **Production scope:** real multi-tenant SaaS.
  - **Time budget:** evenings / weekends only.
  - **Resolution:** downscope to single-user first.
  - **Agentic depth:** learn LangGraph deeply (build agent against mocked tools first).
  - **Phase 2 = agent sandbox** (not bootstrap EKS).
  - **Phase 5 = single-user, your own AWS account** (no cross-account role).
  - **Docs:** (superseded in Session 5) — was "user writes the *why*, AI writes the *what*". Now: comprehensive AI-authored, user-reviewed.
- Updated AGENTS.md: §3 (locked decisions — added product-shape decisions, swapped TanStack→Next.js, added CLI as primary interface, added single-user-first principle, added doc ownership rule); §4 (re-numbered to 6 phases, agent-first); §6.5 (RAG phase references adjusted); §7 (rewrote "What's Coming" for new ordering); §8 (API surface — clarified phase 5 goroutine, added retriever-service endpoints); §9 (naming — added CLI); §10 (cross-cutting rules — added agent-first, CLI-first, doc ownership); §11 (commands — added uv, pnpm, CLI entry points).
- Updated handoff.md (this file): reset phase status, new Session 3 locked decisions, deprecated/changed section, target repo layout, next-session notes for Phase 2 (agent sandbox).
- Will rewrite README.md to match new positioning.

**Carryover to next session (superseded by Sessions 4 and 5):**
- Start Phase 2: agent sandbox at `services/agent-service/`.
- Lay out the directory and write the agent loop end-to-end against mocked tools.
- Run LiteLLM locally on the laptop; no Docker.
- AI writes `docs/langgraph-tools.md`; the user reviews and edits.
- AI writes `docs/strata/agent-architecture.md`; the user reviews and edits.
- When Phase 2 lands, update this handoff with phase-complete status.

### 2026-06-10 — Session 4 (k8s manifests from start)
- User asked for one change: k8s manifests from the start, no docker-compose.
- Confirmed: Phase 2 = agent + LiteLLM, both deployed to a local Kind cluster, both accessed via `kubectl port-forward`. The mocked tools stay mocked; only the *runtime* moves to k8s. LiteLLM proxies to Bedrock via real AWS creds in a k8s Secret (no IRSA in Kind).
- Updated AGENTS.md:
  - §4 Phase 2 row now reads "Agent sandbox in Kind" with "k8s manifests in a local Kind cluster" and "no docker-compose, no EKS — Kind is the dev target"
  - §7 Phase 2 details rewritten with the new directory tree (`control-plane/manifests/`, `strata-dev-kind.yaml`, `Makefile`, Dockerfile for the agent)
  - §10 cross-cutting rules: added "No docker-compose for the platform"
  - §11 commands: replaced laptop-based uv commands with `make kind-up / build / apply / chat / logs-agent / kind-down`
- Updated handoff.md: Phase 2 next-session section rewritten with k8s layout, port-forward-based chat access, in-cluster LiteLLM deployment, and a k8s-flavored "definition of done" checklist.
- Updated README.md: "What's coming" line and Phase 2 row mention Kind; local-dev paragraph now describes `make` targets instead of `uv run` and `docker-compose`.
- Will scaffold Phase 2: `control-plane/`, `strata-dev-kind.yaml`, `Makefile`, `services/agent-service/`, manifests, and the Phase 2 docs (later superseded in Session 5).

**Carryover to next session (superseded by Session 5):**
- Phase 2 scaffold is in flight. Once complete, run `make kind-up && make build && make apply` to bring it up.
- The first end-to-end check is `make chat` (port-forward + curl) returning NDJSON with a `tool_call` for `list_clusters` and a final `done`.
- `docs/langgraph-tools.md` and `docs/strata/agent-architecture.md` are now AI-authored comprehensive refs (Session 5). The user reviews and edits.

### 2026-06-10 — Session 5 (comprehensive docs)

**Trigger:** User changed their mind on the "user writes the *why*,
AI writes the *what*" approach. Asked for the AI to produce
comprehensive docs covering the entire stack — langchain, langgraph,
litellm, rag, bedrock, nextjs — basics, advanced, and anything
needed for the project.

**What changed:**

- Dropped the "stubs for the user to fill in" approach. The
  previous Session 4 carryover said `docs/langgraph-tools.md` and
  `docs/strata/agent-architecture.md` were the user's writing;
  the user said no — make them as comprehensive as possible.
- Replaced the two stub docs with a full `docs/` tree of
  comprehensive references:

  | File | Lines | Topic |
  |---|---|---|
  | `docs/README.md` | index | learning order, by topic, companion docs |
  | `docs/langchain.md` | ~370 | chat models, messages, tools, runnables, output parsers, pitfalls |
  | `docs/langgraph.md` | ~380 | StateGraph, reducers, ToolNode, conditional edges, checkpointers, streaming, debug |
  | `docs/litellm.md` | ~330 | model_list, embeddings, retries, fallbacks, master key, virtual keys, provider swap |
  | `docs/bedrock.md` | ~390 | Nova Pro, Titan v2, SigV4, regions, IAM, Converse API, streaming, throttling, cost |
  | `docs/rag.md` | ~430 | Qdrant collections, retriever-service API, retrieve node, ingestion, chunking, metadata filtering, hybrid search, degraded mode |
  | `docs/nextjs.md` | ~430 | App Router, server components, server actions, streaming tokens, auth, forms, Tailwind, shadcn/ui, pnpm |
  | `docs/strata/agent-architecture.md` | ~340 | the project-specific graph, services, k8s surface, NDJSON wire format, what's deferred |

- Updated `AGENTS.md`:
  - §3 locked decisions: replaced "you write the *why*, AI writes
    the *what*" with "comprehensive AI-authored, user-reviewed"
  - §10 cross-cutting rules: replaced the doc-ownership rule
    with the new "comprehensive AI-authored docs" + "hand-written
    learning notes welcome" rules
- Updated `handoff.md` (this file): changed the Session 3 locked
  decision on doc ownership, added this Session 5 entry.

**Carryover to next session:**

- Phase 2 code is in place; `pytest` is green (11/11); ruff is
  clean; k8s manifests validate with `kubectl apply --dry-run`.
- Run `cp control-plane/manifests/10-litellm/secret.yaml.example
  control-plane/manifests/10-litellm/secret.yaml`, fill in AWS
  creds, then `make kind-up && make build && make apply && make chat`.
- When Phase 2 lands end-to-end in the cluster, mark it
  phase-complete in this handoff and start Phase 3.
- The docs are now full references. The user will review and
  edit; future updates should follow the same comprehensive
  style. Hand-written "What I learned the hard way" sections
  are welcome in any doc.
