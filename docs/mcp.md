# MCP — Model Context Protocol

> **Stub for Phase 0.** Full doc lands in Phase 1 alongside the
> FastMCP k8s server.

The Model Context Protocol (MCP) is the wire protocol Strata uses
for tool calling between the agent and the backend's cluster-facing
servers. We use FastMCP 3.x over streamable-HTTP transport.

Key references:

- `notes/fastmcp-tutorial/mcp-curriculum/` — the user's existing
  curriculum. Will be ported to `docs/mcp/` deep-dive in Phase 1.
- [MCP spec](https://modelcontextprotocol.io/)

Planned outline for `docs/mcp.md`:

1. What MCP is (one paragraph)
2. Transports: stdio vs HTTP/SSE vs streamable-HTTP
3. The four primitives: tools, resources, prompts, context
4. FastMCP 3.x server scaffolding
5. Client patterns (the agent side)
6. Auth: passing the user's JWT through MCP calls
7. Our deployment pattern (one MCP server per concern: k8s,
   argocd, aws, helm)
8. What to read next