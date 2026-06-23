# Strata backend architecture

> **Stub for Phase 0.** Full doc lands in Phase 1.

Internal design of the backend that runs in the user's managed
k8s cluster. Audience: anyone modifying `backend/`.

Outline:

1. The service catalog
   - orchestrator (Go, chi, sqlx)
   - retriever (Go)
   - rag-indexer (Go)
   - agent-service (Python, FastAPI, LangGraph)
   - litellm (Python, hosted LLM proxy)
   - mcp-servers (Python, FastMCP)
   - web (Next.js)
   - postgres (CloudNativePG)
   - qdrant
   - keycloak
   - envoy-gateway
2. Multi-tenancy: per-user JWT, per-user encryption DEK, per-user
   Qdrant collection
3. RBAC: orchestrator enforces cluster ownership; MCP servers
   trust the orchestrator's forwarded user identity
4. Data flow: TUI → Envoy → orchestrator → MCP → k8s
5. What to read next