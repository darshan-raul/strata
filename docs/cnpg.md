# CloudNativePG (CNPG)

> **Stub for Phase 0.** Full doc lands in Phase 1.

[CloudNativePG](https://cloudnative-pg.io/) is the PostgreSQL
operator Strata runs in the backend. Replaces RDS.

Why in-cluster Postgres (CNPG) over RDS:

- No AWS account dependency for the backend's metadata DB
- Backup via `barman` plugin to S3 (Phase 8+)
- Point-in-time recovery via WAL archiving
- Failover via the operator
- Declarative — defined in Helm, GitOps-friendly

What goes in Postgres:

- `users` — Keycloak-synced user records (lightweight metadata
  the orchestrator caches)
- `clusters` — registered clusters (one row per cluster the
  user has added)
- `cluster_credentials` — encrypted kubeconfigs (AES-GCM ciphertext)
- `actions` — audit log of TUI / agent / web actions
- (Phase 6+) `rag_chunks` metadata — pointer rows for RAG
  indexing status

Encryption: the `cluster_credentials.ciphertext` column is
encrypted with a per-user DEK, which is wrapped by a
backend KMS key.

Planned outline:

1. The Postgres-in-cluster argument
2. Installing CNPG via Helm
3. Cluster definition (`Cluster` CRD)
4. Backups (barman → S3)
5. Failover and HA
6. Connection from the orchestrator (pgx, service DNS)
7. Migration tooling
8. What to read next