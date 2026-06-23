# Strata MCP architecture

> **Stub for Phase 0.** Full doc lands in Phase 1.

How Strata uses the Model Context Protocol (MCP).

Outline:

1. Why MCP (vs function calling directly in the agent)
2. The MCP server catalog
   - k8s (Phase 1 read, Phase 3 mutations)
   - argocd (Phase 7)
   - aws (Phase 7, read-only)
   - helm (Phase 7)
3. Transport: streamable-HTTP via FastMCP 3.x
4. Auth: per-request JWT, MCP server maps to user's stored k8s
   credentials
5. Tool description conventions (the docstring is the contract)
6. Mutation tools — marked as such, require confirmation
7. Deployment: one `Deployment` + `Service` per MCP server,
   namespaced by concern
8. What to read next