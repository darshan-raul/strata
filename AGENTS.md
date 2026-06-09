# AGENTS.md — Strata Platform

## What This Project Is

Strata is a SaaS platform that provisions production-grade EKS clusters in customers' AWS accounts via GitOps and a serverless control plane. The `sample-app/` subdirectory is a **sample application** used to test cluster deployment — it is NOT the Strata platform itself.

## Repo Architecture

| Directory | Purpose |
|-----------|---------|
| `lambdas/` | Strata serverless control plane (Python Lambdas) |
| `infra/` | Strata control plane Terraform (Cognito, DynamoDB, S3, IAM, Step Functions, CodeBuild) |
| `flutter_app/` | Flutter mobile + web app for the Strata platform |
| `terraform/aws/` | EKS cluster Terraform module (zipped to S3 for CodeBuild) |
| `buildspec.yml` | CodeBuild spec — runs Terraform in customer AWS account |
| `onboarding_cfn.yaml` | CloudFormation template customers deploy to create cross-account IAM roles |
| `sample-app/` | Sample application (Go microservices + React portal-ui) — EKS deployment target |
| `diagrams/` | Architecture diagrams (PNG) |
| `specs/` | Master design docs and sample app architecture |

## Strata Platform (Serverless Backend)

### Lambdas (`lambdas/`)

Only `orchestrator/` exists. The rest are not yet created.

| Lambda | Status | Purpose |
|--------|--------|---------|
| `orchestrator/` | Implemented (`handler.py`) | Validates requests, writes to DynamoDB, starts Step Functions |
| `status_checker/` | Not yet created | EKS API + CloudWatch queries via cross-account STS |
| `argocd_deployer/` | Not yet created | Helm install + ArgoCD API registration |
| `agent_proxy/` | Not yet created | Bedrock Agent relay |
| `agent_tools/` | Not yet created | K8s queries via EKS API + cloud monitors for Bedrock |
| `health_monitor/` | Not yet created | EventBridge-triggered periodic health checks |

### DynamoDB Tables (`infra/dynamodb.tf`)

- **`clusters`** — `user_id` (PK), `cluster_id` (SK). Tracks EKS cluster lifecycle (INITIATED → PROVISIONING → VALIDATING → INSTALLING_ARGOCD → READY → FAILED/DELETING/DELETED).
- **`alerts`** — `user_id` (PK), `alert_id` (SK). Stores health monitoring alerts.

### API Gateway Routes (`infra/api_gateway.tf`)

All routes authorized via Cognito JWT. Lambdas handle orchestration; DynamoDB handles direct reads.

- `POST /clusters` — Provision new cluster
- `DELETE /clusters/{cluster_id}` — Deprovision cluster
- `GET /clusters` — List user clusters
- `GET /clusters/{cluster_id}` — Fast status poll
- `GET /dashboard/summary` — Aggregate counts
- `POST /agent/chat` — Bedrock Co-Pilot
- `PUT /users/me/github-token` — Store GitHub token

### Step Functions

State machine definitions (`provision_cluster.asl.json`, `deprovision.asl.json`) are **not yet created**. They will live in `state_machines/` once created.

## Strata Platform: Flutter App (`flutter_app/`)

Flutter app for Android + Web. Currently minimal stub (`lib/main.dart`, `config.dart`, `screens/`, `services/`, `models/`, `theme/`).

- Run locally: `cd flutter_app && flutter run`
- Build web: `cd flutter_app && flutter build web`

## Infrastructure (`infra/`)

Terraform for the Strata control plane. State is managed in S3 backend (per `main.tf`).

- Key files: `cognito.tf`, `dynamodb.tf`, `iam.tf`, `step_functions.tf`, `codebuild.tf`, `lambdas.tf`, `api_gateway.tf`, `secrets_manager.tf`
- Variables: defined in `variables.tf`

## Infrastructure (`terraform/aws/`)

EKS cluster Terraform module. Zipped to S3 and extracted by CodeBuild during provisioning.

- `eks.tf`, `vpc.tf`, `outputs.tf`, `variables.tf`, `provider.tf`

## Onboarding CloudFormation (`onboarding_cfn.yaml`)

Customer deploys this to their AWS account. Creates:
- `strata-platform-provisioner` role (cross-account Terraform access)
- `strata-platform-reader` role (status checking via STS assume role)

## Sample Application (`sample-app/`)

The sample app is a cloud-native mirror of the Strata serverless backend, deployed to EKS clusters created by the platform.

### Go Services (`sample-app/services/`)

Each service is a standalone Go module. They are lint-checked by `.github/workflows/go-services.yml`.

| Service | Port | Path |
|---------|------|------|
| catalog-service | 8081 | `sample-app/services/catalog-service` |
| provisioner-service | 8082 | `sample-app/services/provisioner-service` |
| scorecard-service | 8083 | `sample-app/services/scorecard-service` |
| workflow-service | 8084 | `sample-app/services/workflow-service` |
| audit-service | 8085 | `sample-app/services/audit-service` |

Lint rules and service-specific notes are in `sample-app/AGENTS.md`.

### Portal UI (`sample-app/services/portal-ui/`)

React/Vite app with no `package-lock.json` (npm caching is disabled in the CI workflow).

### Docker Compose (`sample-app/docker-compose.yml`)

Local dev environment: PostgreSQL, NATS, Kong, Dex, and all 5 Go services.

### K8s Manifests (`sample-app/k8s/`)

Kubernetes manifests for the sample app. Used with ArgoCD GitOps sync. Not yet created.

### Tiltfile (`sample-app/Tiltfile`)

Used for local Kind cluster development. Run with `cd sample-app && tilt up`.

## Build & Deploy Flow

1. User triggers cluster provisioning from Flutter app
2. `orchestrator` Lambda writes `INITIATED` to DynamoDB and starts Step Functions
3. Step Functions invokes CodeBuild (`buildspec.yml`)
4. CodeBuild downloads EKS Terraform module from S3, runs `terraform apply` in customer account via STS assume role
5. `status_checker` validates cluster is `ACTIVE`
6. `argocd_deployer` configures ArgoCD to sync from user's ops repo
7. Cluster marked `READY`

## CI Workflows

- `.github/workflows/go-services.yml` — Matrix builds for all 5 Go services (lint + test)
- `.github/workflows/node-service.yml` — Portal UI build and lint

### Local Workflow Testing with `act`

Run GitHub Actions locally without pushing commits.

**Installation:**
```bash
# Download and install act binary
curl -sL https://github.com/nektos/act/releases/download/v0.2.88/act_Linux_x86_64.tar.gz | tar -xz
mv act ~/bin/act
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
```

**Configuration** (`~/.config/act/actrc`):
```
-P ubuntu-latest=ghcr.io/catthehacker/ubuntu:runner-latest
```

**Usage:**
```bash
# Run all workflows (uses push event by default)
act

# Run specific workflow
act -W .github/workflows/node-service.yml
act -W .github/workflows/go-services.yml

# Run specific job
act -W .github/workflows/go-services.yml -j build-test-lint-scan-deploy

# Run with workflow_dispatch (interactive)
act -W .github/workflows/go-services.yml -e workflow_dispatch

# Use cached actions (faster, no network)
act --action-offline-mode
```

**Notes:**
- Go services matrix runs all 5 services in parallel
- First run downloads Docker images (~1GB), subsequent runs use cache
- Auth errors for private repos: run `gh auth login`

## Not Yet Created

- Step Functions state machines (`state_machines/provision_cluster.asl.json`, `deprovision.asl.json`)
- Lambdas: `status_checker`, `argocd_deployer`, `agent_proxy`, `agent_tools`, `health_monitor`
- Sample app K8s manifests (`sample-app/k8s/`)
- Sample app React frontend (only Go services + portal-ui exist)

## Quick Commands

```bash
# Package Lambdas for deployment
cd lambdas && bash package.sh

# Local sample app dev (Docker Compose)
docker-compose -f sample-app/docker-compose.yml up

# Kind cluster + Tiltfile dev
kind create cluster && cd sample-app && tilt up

# Flutter app
cd flutter_app && flutter run

# Terraform (infra — requires S3 backend configured)
cd infra && terraform init && terraform plan
```

## General Guidelines

- **DO NOT commit changes unless explicitly requested by the user**