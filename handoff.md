# handoff

> Live cross-session state for Strata v2. The last agent to leave
> the repo updates this file before signing off. New agents read
> AGENTS.md first, then this file.

---

## Current phase

**Phase 0 — Reset + TUI graduation.** (in progress)

The full plan is in [AGENTS.md](AGENTS.md). Phase 0 deletes the
stale pre-v2 files, graduates `sandbox/linux-tui/` to top-level
`tui/strata_tui/`, rewrites AGENTS.md / README.md, and stubs out
`docs/`.

---

## What's done in this session

- [x] Project rescoped: v1 was a "Strata provisions EKS via Cognito
  + Step Functions + Flutter" SaaS. v2 is a two-tier TUI + multi-tenant
  backend system focused on managing **existing** clusters.
- [x] Re-litigated locked decisions with the user. Decisions captured
  in [AGENTS.md §2](AGENTS.md#2-locked-decisions-do-not-re-litigate).
  Notable changes from the old plan:
  - **Ingress:** no nginx-ingress, no Kong. **Envoy Gateway** + AWS
    NLB.
  - **OIDC:** no Zitadel. **Keycloak.**
  - **k8s auth:** built-in context registry in the backend, with
    per-user creds encrypted at rest.
  - **MCP:** all servers run in the backend k8s cluster; streamable
    HTTP transport.
  - **RAG:** per-user Qdrant collections in the backend.
  - **TUI scope:** read + write via direct kubectl-style commands
    (k9s-like) plus the agent chat rail. Mutations go through a
    confirmation modal.
  - **Lifestyle:** full reset of the repo, but keep the existing
    notes/ deep-dives and graduate the working `sandbox/linux-tui/`
    TUI.
- [x] `AGENTS.md` rewritten for v2.
- [x] `README.md` rewritten for v2.

## What's next (Phase 0 close-out)

- [x] Delete stale: `specs/strata_master_doc.md`,
  `specs/sample_app_architecture.md`, `services/agent-service/`,
  `cli/`, `sandbox/`, `onboarding/`, old CI workflows, old
  `Makefile`, `strata-dev-kind.yaml`.
- [x] Graduate `sandbox/linux-tui/` → `tui/strata_tui/`. Renamed
  the package, the project in `pyproject.toml`, the entry point,
  and the test imports. Stripped the "sandbox / not part of
  Strata" disclaimers. Stripped the "LangChain only" constraint
  (LangGraph is now in the dependency list for Phase 1).
  Replaced the six Linux-specific tools with a placeholder
  `echo` tool (real k8s + MCP tools land in Phase 1).
- [x] Port `notes/langchain/` → `docs/langchain/`,
  `notes/langgraph/` → `docs/langgraph/`. Port
  `notes/litellm.md`, `notes/bedrock.md` to `docs/`. Stub
  `docs/rag.md` (rewrite for per-user lands in Phase 6).
- [x] Created directory skeleton: `backend/`, `web/`, `infra/`,
  plus `docs/` subdirs for `mcp/`, `textual/`, `keycloak/`,
  `envoy-gateway/`, `kubernetes/`, `cnpg/`,
  `external-secrets/`, `strata/`.
- [x] Stubbed `.github/workflows/tui.yml`, `backend.yml`,
  `web.yml`.
- [x] New top-level `Makefile` with `tui-dev`, `tui-test`,
  `tui-lint`, `backend-up`, `backend-down`, `backend-logs`,
  `backend-rebuild`, `reset`.
- [x] New `.gitignore`. `notes/` gitignored as the personal
  scratchpad (canonical versions live in `docs/`).
- [x] **Verification:** `cd tui && uv sync --all-extras && uv run
  --all-extras pytest` → 6 tests pass. `make tui-lint` → clean.
  App boots headless, status bar shows
  `model: MiniMax-M3 | ready | ...`, history widget renders,
  input widget renders. Live MiniMax call requires the user to
  set `MINIMAX_API_KEY` in `tui/.env` (or in the shell env)
  before `make tui-dev`.

### Phase 0 — done

Ready for Phase 1.

## What's next (Phase 1+)

See [AGENTS.md §5](AGENTS.md#5-build-phases).

- **Phase 1:** Backend skeleton on local kind. Go orchestrator with
  Postgres + JWT auth. FastMCP `k8s` server with read-only `:get`
  tools. End-to-end `tui :get pods` flow.
- **Phase 2:** Keycloak in the backend. Next.js web with signup/login.
  TUI `strata login` (OIDC device code). JWT propagation.
- **Phase 3:** Mutation tools + confirmation (TUI modal + LangGraph
  `interrupt()`).
- **Phase 4:** Encrypted cluster registry. Web "Add cluster" form.
  AES-GCM, KMS-wrapped DEK.
- **Phase 5:** Web dashboard (cluster list, per-cluster resource
  browser, action history).
- **Phase 6:** RAG (per-user). Qdrant, rag-indexer, retriever-service,
  `retrieve` node.
- **Phase 7:** ArgoCD MCP, AWS MCP, Helm MCP.
- **Phase 8:** Real EKS via `infra/bootstrap/`.
- **Phase 9:** Polish + CI + observability.

---

## Open questions / risks to revisit

1. **Envoy Gateway + OIDC.** The user said "Envoy can do it via
   some plugins." We need to decide between (a) Envoy Gateway's
   built-in ext-authz + an OIDC filter and (b) `oauth2-proxy`
   sidecars in front of services. Resolve in Phase 2.
2. **KMS-wrapped DEK** vs. a single master key in a k8s Secret for
   cluster-credential encryption. Decision: KMS-wrapped DEK for
   prod (Phase 8), single-key fallback for kind dev (Phase 4).
3. **Local-dev target.** Backend in `kind` matches the old plan and
   is convenient. Confirm before Phase 1.
4. **MCP auth.** The agent in the backend calls MCP servers; the
   servers validate the user's JWT and look up the user's
   encrypted cluster creds. Confirm during Phase 1.
5. **TUI LLM key source.** Recommended: env var first, OS keyring
   via `keyring` PyPI as fallback. Confirm during Phase 0 / 1.

---

## Notes for the next session

- The currently working TUI lives at `sandbox/linux-tui/` (before
  this session finishes, it will be `tui/strata_tui/`). It already
  demonstrates the chat + tool-call + confirmation-modal pattern
  we want. The Linux-specific tools (`list_dir`, `read_file`,
  `grep`, `system_info`, `disk_usage`, `run_command`) will be
  replaced in Phase 1 with k8s + MCP tools.
- The `notes/fastmcp-tutorial/mcp-curriculum/` content is the
  starting point for `docs/mcp/` and the eventual
  `backend/mcp-servers/` Python servers.
- The `notes/langchain/` and `notes/langgraph/` deep-dives are
  already in good shape. The TUI's "LangChain only" constraint is
  the only thing that needs to change; LangGraph will be added in
  Phase 1.

---

## Session log

### Session 1 — rescope + Phase 0 setup (current)

- Rescoped the project from the old "Strata provisions EKS" SaaS
  to the new "TUI + multi-tenant backend" two-tier model.
- Re-litigated locked decisions with the user.
- Rewrote `AGENTS.md` and `README.md` for v2.
- Created this `handoff.md`.
- Next: complete the Phase 0 file moves, doc ports, and
  skeleton creation; verify the TUI smoke test still passes.
