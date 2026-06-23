# Kubernetes (in Strata)

> **Stub for Phase 0.** Full doc lands in Phase 1.

Strata manages **existing** Kubernetes clusters. We don't
provision them — the user brings their own clusters, registers
them with the backend, and the backend's MCP `k8s` server talks
to them on their behalf.

The MCP k8s server uses:

- **Python:** [`kubernetes`](https://github.com/kubernetes-client/python)
  Python client (preferred for the FastMCP server, which is Python).
- **Go:** [`client-go`](https://github.com/kubernetes/client-go)
  for any Go service that needs to talk to k8s (orchestrator,
  rag-indexer).

Both clients read a kubeconfig to construct an API client. The
backend's MCP server loads the user's kubeconfig from the
encrypted cluster registry per request.

The TUI never sees a kubeconfig. It calls
`orchestrator → MCP k8s server` over HTTPS, authenticated with
the user's JWT.

Planned outline:

1. The kubeconfig shape and what we extract from it
2. ServiceAccount tokens vs user tokens vs OIDC tokens
3. The `kubernetes` Python client patterns we'll use
4. Reading resources (`list`, `read`, `logs`)
5. Mutations (`delete`, `apply`, `exec`) and confirmation
6. Per-user RBAC: how the MCP server maps the JWT to a SA token
7. Resource kinds we'll expose (Pods, Services, Deployments,
   StatefulSets, ConfigMaps, Secrets, Events, Logs)
8. What to read next