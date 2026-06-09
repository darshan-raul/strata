# AGENTS.md — Strata sample-app

The sample application is the deployment target for Strata-provisioned EKS clusters. It is **not** the Strata platform itself; it is a Go microservices mirror that exercises the cluster-provisioning workflow.

## Repo Structure

- `sample-app/` — main application workspace (Go monorepo + portal-ui)
  - `go.work` — Go workspace file; all 5 services must be listed here
  - `services/` — contains the 5 Go services and portal-ui
  - `docker-compose.yml` — local dev environment (Postgres, NATS, Redis)

## Go Services

| Service | Port | Path |
|---------|------|------|
| catalog-service | 8081 | `sample-app/services/catalog-service` |
| provisioner-service | 8082 | `sample-app/services/provisioner-service` |
| scorecard-service | 8083 | `sample-app/services/scorecard-service` |
| workflow-service | 8084 | `sample-app/services/workflow-service` |
| audit-service | 8085 | `sample-app/services/audit-service` |

Each service has its own `go.mod`. Dependencies are NOT hoisted to `sample-app/`.

## CI Workflows

- `.github/workflows/go-services.yml` — lints and tests all 5 Go services via matrix
- `.github/workflows/node-service.yml` — builds/lints portal-ui (Node.js 20)

## Lint Rules (golangci-lint)

All services must pass with `errcheck` enabled. Common missed error checks:

- `json.NewEncoder(w).Encode(v)` — always check the error
- `db.QueryRow(...).Scan(&var)` — always check the error
- `db.Query(...).Scan(...)` inside rows.Next() loops — always check the error
- `db.Exec(...)` — always check the error (discard with `_` or log it)
- `nc.Publish(...)` — always check the error
- `nc.Subscribe(...)` — always check the error (capture it: `if _, err := nc.Subscribe(...)`)
- `rows.Close()` in defer — already correct, but `rows` from `db.Query(...)` can be nil; check before defer

Template for scan in a loop:
```go
if err := rows.Scan(&val); err != nil {
    log.Printf("scan error: %v", err)
    continue
}
```

Template for Publish/Subscribe:
```go
if err := nc.Publish("subject", payload); err != nil {
    log.Printf("publish error: %v", err)
}
```


## Commands

```bash
# Lint a single service
golangci-lint run --path-prefix=sample-app/services/catalog-service --timeout=5m

# Test a single service
cd sample-app/services/catalog-service && go test -v ./...

# Run portal-ui linter
cd sample-app/services/portal-ui && npm run lint
```