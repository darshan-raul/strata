# Envoy Gateway

> **Stub for Phase 0.** Full doc lands in Phase 1 (Helm install)
> and Phase 2 (OIDC integration).

[Envoy Gateway](https://gateway.envoyproxy.io/) is Strata's
ingress. Replaces nginx-ingress and Kong from the v1 plan.

Why Envoy Gateway:

- Native [Gateway API](https://gateway-api.sigs.k8s.io/) support
  (the new standard, replacing Ingress)
- Native `ext-authz` for Keycloak JWT validation
- Native rate limiting
- Single Envoy control plane + data plane, simple to operate
- AWS NLB in front for stable external IPs

End-to-end traffic path in production:

```
TUI / browser
   │
   │ HTTPS
   ▼
AWS NLB
   │
   ▼
Envoy Gateway (Gateway API)
   │  ext-authz → Keycloak JWT validation
   │
   ├─▶ web (Next.js)
   ├─▶ orchestrator (Go)
   ├─▶ agent-service (Python)
   ├─▶ retriever (Go)
   └─▶ rag-indexer (Go)
```

Envoy Gateway is also responsible for TLS termination, with certs
managed by cert-manager (also a separate topic — see
`docs/cert-manager.md` in Phase 8).

Planned outline:

1. Gateway API primitives (Gateway, GatewayClass, HTTPRoute)
2. Installing Envoy Gateway via Helm
3. AWS NLB provisioning (annotations, health checks)
4. `ext-authz` + Keycloak JWT
5. Rate limiting (`EnvoyFilter` or native `RateLimitFilter`)
6. TLS via cert-manager + ACM
7. Routing rules for each backend service
8. Debugging (Envoy access logs, `/config_dump`)
9. What to read next