# Strata data flow

> **Stub for Phase 0.** Full doc lands in Phase 1.

End-to-end request paths through Strata.

Outline:

1. TUI chat message
   - User types "list my failing pods"
   - TUI calls orchestrator's `/chat` endpoint with JWT
   - Orchestrator forwards to agent-service
   - Agent-service LangGraph: `call_model` → `ToolNode`
     (`k8s_list_pods`) → orchestrator (looks up user creds) →
     MCP k8s server → user cluster
   - Response streams back as NDJSON
   - TUI renders streamed tokens
2. TUI kubectl-style `:get pods`
   - Direct REST call to orchestrator
   - Orchestrator → MCP k8s server → user cluster
   - Result returned as JSON
   - TUI renders in `DataTable`
3. TUI mutation (Phase 3+)
   - User types `:delete pod X`
   - TUI pops confirmation modal
   - User confirms
   - Same path as `:get` but flagged as MUTATION
4. Web signup
   - User visits web signup
   - Web calls orchestrator to create Keycloak user
   - User verifies email
   - Web issues session cookie
5. TUI login (Phase 2)
   - TUI requests device code from Keycloak
   - TUI shows URL + code
   - User visits URL in browser, signs in, authorizes device
   - TUI polls for token
   - TUI stores JWT locally
6. What to read next