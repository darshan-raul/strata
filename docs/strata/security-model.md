# Strata security model

> **Stub for Phase 0.** Full doc lands in Phase 4 (cluster
> credential encryption) and evolves through Phase 8.

Outline:

1. Trust boundaries
   - User laptop (TUI) — BYOK LLM key, JWT to backend
   - Backend k8s cluster — TLS, JWT validation at Envoy
   - User's clusters — short-lived tokens issued by the MCP
     server per request
2. Threat model
3. Authentication
   - OIDC via Keycloak
   - TUI uses device-code flow
   - Web uses auth-code flow
4. Authorization
   - RBAC at the orchestrator (cluster ownership)
   - RBAC at the MCP server (what tools, which cluster)
5. Encryption at rest
   - Cluster creds: AES-GCM with per-user DEK wrapped by KMS
   - Postgres: encrypted at rest (CNPG + EBS encryption)
   - Qdrant: per-user collections, encrypted at rest
6. Encryption in transit
   - TLS everywhere (Envoy Gateway termination)
   - Cluster-to-cluster mTLS via the MCP server's per-request
     SA token
7. Audit log (Phase 1 — every action goes through the
   orchestrator)
8. What to read next