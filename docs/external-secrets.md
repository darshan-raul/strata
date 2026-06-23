# External Secrets Operator (ESO)

> **Stub for Phase 0.** Full doc lands in Phase 1.

[External Secrets Operator](https://external-secrets.io/)
syncs secrets from external providers (AWS Secrets Manager,
HashiCorp Vault, etc.) into k8s `Secret` resources. Strata uses
AWS Secrets Manager as the source of truth for long-lived
secrets.

Why ESO instead of literal `Secret` resources in Helm:

- KMS-backed at rest
- Auto-rotation
- Single audit trail for secret reads
- GitOps-friendly: the manifest declares "this secret exists in
  Secrets Manager and is mapped to this k8s Secret"; the value
  never lives in git

What lives in Secrets Manager:

- The orchestrator's database password
- The litellm master key + provider API keys (Phase 1+)
- The encryption KMS key for cluster credentials (Phase 4+)
- The Keycloak admin password
- (Phase 8+) TLS cert private keys (via cert-manager + ESO)

Planned outline:

1. The git-secrets argument
2. Installing ESO via Helm
3. `SecretStore` and `ExternalSecret` CRDs
4. AWS Secrets Manager backend + IRSA
5. Refresh intervals
6. Rotation
7. Fallback for kind dev (a literal Secret)
8. What to read next