# Strata Platform — Workflows

---

## Premise

The target user is a developer or team who has an existing codebase and wants a fully managed, AI-assisted platform to:

1. **Analyze their codebase** — The Bedrock AI agent deeply parses the user's code to understand the language, frameworks, services, and logical boundaries. It then:
   - Applies **auto-instrumentation** (OpenTelemetry SDKs injected at the framework level).
   - Identifies **manual tracing opportunities** — e.g. critical business logic paths, async jobs, DB calls — and injects spans there.
   - Adds **structured logging** in places where log coverage is missing (e.g. error handlers, service entry/exit points, retry blocks).
   - Adds **metrics** at meaningful points (e.g. request counters, queue depths, cache hit/miss ratios).
   - Generates a **Dockerfile** appropriate for the detected runtime/build system.
   - Generates complete **Kubernetes manifests** (Deployment, Service, HPA, ConfigMap, and optional Ingress).

2. **Provide an "ops repo" for ArgoCD** — Rather than creating a GitHub repo on the user's behalf (too risky with OAuth2 token scope), the agent generates a step-by-step guide instructing the user to create a new empty GitHub repo. This repo will contain the K8s manifests and becomes the ArgoCD Application source. The user provides the URL to this repo at cluster provision time.

3. **Provision Kubernetes infrastructure** — Spins up an EKS cluster (v1) in the customer's AWS account using Terraform executed via CodeBuild, orchestrated via Step Functions. ArgoCD is installed via Helm and automatically registered to the user's ops repo.

4. **Monitor continuously** — A scheduled EventBridge rule periodically triggers a health-check Lambda that queries EKS + CloudWatch, writes anomalies to DynamoDB, and can trigger push notifications. The Bedrock Co-Pilot agent answers ad-hoc queries and can surface the same health data on demand.

---

## Workflow 1 — Initial Onboarding

### Step 1 — Sign Up

1. User opens the Observatory Flutter app and navigates to the signup screen.
2. User enters **email + password** → Cognito `signUp` API call.
3. Cognito sends a **verification email**; user enters the code in-app.
4. On successful verification, a Cognito user record is created. A **per-user `external_id`** (UUID v4) is generated server-side and stored in two places:
   - DynamoDB `users` table: `{ user_id (PK), external_id, created_at }`
   - Cognito custom attribute: `custom:external_id`
   
   > **Why here?** The `external_id` must exist before the CloudFormation link is generated (Step 3). Generating it at signup avoids a separate API round-trip later.

5. App navigates to Step 2.

---

### Step 2 — Connect GitHub (OAuth2)

1. App displays the **"Connect GitHub"** screen.
2. User taps **"Connect GitHub Account"**.
3. App opens an in-app WebView to the GitHub OAuth2 authorization URL:
   ```
   https://github.com/login/oauth/authorize
     ?client_id=<STRATA_GITHUB_APP_CLIENT_ID>
     &scope=repo,read:user
     &state=<csrf_token>
   ```
4. User authorizes the app on GitHub. GitHub redirects to the registered callback URI (`strata://callback?code=<code>&state=<state>`).
5. App intercepts the callback, validates the `state`, and sends `code` to the backend:
   ```
   PUT /users/me/github-token
   Body: { "code": "<oauth_code>" }
   ```
6. The `orchestrator` Lambda:
   - Exchanges the code for an access token via `POST https://github.com/login/oauth/access_token`.
   - Stores the token in Secrets Manager: `strata/users/{user_id}/github → { "token": "..." }`.
   - Stores `custom:github_connected = "true"` as a Cognito custom attribute.
7. App navigates to Step 3.

---

### Step 3 — Cloud Credentials (AWS IAM via CloudFormation)

**Goal:** Grant Strata's AWS account the ability to create resources in the customer's AWS account, using a cross-account IAM role with a per-user `external_id`.

#### 3a. User enters AWS Account ID

1. App shows the **Cloud Credentials** screen with three provider cards (AWS active, Azure/GCP "Coming Soon").
2. User enters their **12-digit AWS Account ID** in the text field.
3. User taps **"Generate Setup Link"**.

#### 3b. Backend generates the CloudFormation deep-link

The app calls:
```
GET /onboarding/cloudformation-url?account_id={aws_account_id}
```

A dedicated **`onboarding` Lambda** handles this:
1. Reads the user's `external_id` from DynamoDB (`users` table, keyed by Cognito `sub`).
2. Generates a **pre-signed S3 URL** (TTL: 1 hour) pointing to the `onboarding_cfn.yaml` template stored in the Strata platform S3 bucket.
3. Constructs the one-click AWS Console deep-link, embedding the `external_id` as a CloudFormation parameter:
   ```
   https://console.aws.amazon.com/cloudformation/home#/stacks/create/review
     ?templateURL=<presigned-s3-url>
     &stackName=strata-platform-roles
     &param_StrataAccountId=<STRATA_PLATFORM_ACCOUNT_ID>
     &param_ExternalId=<user_external_id>
   ```
4. Returns `{ "cloudformation_url": "...", "external_id": "..." }` to the Flutter app.

#### 3c. User deploys the CloudFormation stack

The app shows a **step-by-step guidance panel**:
- Step 1: Copy/open the link (opens in system browser).
- Step 2: Review the stack parameters (pre-filled — Account ID and External ID).
- Step 3: Check the IAM acknowledgement checkbox.
- Step 4: Click "Create Stack" and wait ~60 seconds.

The `onboarding_cfn.yaml` creates two IAM roles in the customer's account:

| Role | Purpose |
|------|---------|
| `strata-platform-provisioner` | Assumed by CodeBuild/Step Functions — has permissions to create VPC, EKS, IAM, etc. |
| `strata-platform-reader` | Assumed by status_checker + agent_tools Lambdas — read-only EKS/CloudWatch access. |

Both roles have a trust policy scoped to Strata's AWS account with the user's unique `external_id`:
```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<STRATA_ACCOUNT_ID>:root" },
  "Action": "sts:AssumeRole",
  "Condition": { "StringEquals": { "sts:ExternalId": "<user_external_id>" } }
}
```

#### 3d. Verification

1. User taps **"Verify Setup"** in the app.
2. App polls `GET /onboarding/verify-iam?account_id={id}` (max 5 retries, 10s apart).
3. The `onboarding` Lambda:
   - Fetches the user's `external_id` from DynamoDB.
   - Calls `sts:AssumeRole` against `arn:aws:iam::{aws_account_id}:role/strata-platform-reader` using the `external_id`.
   - Returns `{ "verified": true }` on success, `{ "verified": false, "reason": "..." }` on failure.
4. On verified → stores `custom:aws_account_id` in Cognito + `aws_account_id` in DynamoDB `users` table → navigates to Dashboard.

---

## Workflow 2 — Cluster Provisioning

### Trigger

User taps **"+"** FAB on Dashboard → navigates to Provision screen → fills in:
- **Cluster Name** (e.g. `PROD-NORTH-01`)
- **Provider**: AWS (only active in v1)
- **Region**: one of 5 AWS regions
- **Instance Type**: `t3.medium | t3.large | m5.large | m5.xlarge`
- **Ops Repo URL**: the GitHub URL of their pre-created ops repo (the ArgoCD source)

User taps **"LAUNCH CLUSTER"** → confirmation dialog → `POST /clusters`.

### Sequence

```
Flutter App
    │  POST /clusters { name, provider, region, instance_type, github_repo }
    ▼
API Gateway (Cognito JWT authorizer)
    │
    ▼
orchestrator Lambda
    │  1. Reads user's aws_account_id + external_id from Cognito claims / DDB
    │  2. Generates cluster_id = "eks-{user_id[:8]}-{uuid[:6]}"
    │  3. Writes DynamoDB item (status=INITIATED, current_step=STARTED)
    │  4. Starts Step Functions execution
    │  5. Returns 202 { cluster_id, status: "INITIATED" }
    ▼
Step Functions — provision_cluster.asl.json
    │
    ├─► UpdateStatusProvisioning (DynamoDB: status=PROVISIONING, step=TERRAFORM_APPLY)
    │
    ├─► RunTerraform
    │       └─ Invokes StartCodeBuild Lambda (waitForTaskToken pattern)
    │               └─ Starts CodeBuild project with:
    │                      - Terraform module zipped in S3
    │                      - Variables: cluster_name, region, instance_type,
    │                        aws_account_id, external_id
    │               └─ CodeBuild assumes strata-platform-provisioner role
    │                  (cross-account, using external_id) to run terraform apply
    │               └─ On success: sends task token back → SFN continues
    │               └─ Terraform outputs: cluster_endpoint, argocd_url,
    │                  argocd_admin_password
    │
    ├─► UpdateStatusValidating (DynamoDB: status=VALIDATING, step=CLUSTER_HEALTH_CHECK)
    │
    ├─► ValidateCluster
    │       └─ status_checker Lambda: assumes strata-platform-reader,
    │          calls eks:DescribeCluster, waits for ACTIVE status
    │
    ├─► UpdateStatusInstallingArgoCD (DynamoDB: status=INSTALLING_ARGOCD, step=HELM_ARGOCD)
    │
    ├─► DeployAndRegisterArgoCD
    │       └─ argocd_deployer Lambda:
    │              1. Reads GitHub token from Secrets Manager
    │              2. Waits for ArgoCD to be healthy (/healthz)
    │              3. Logs in → gets bearer token
    │              4. Registers the ops repo (github_repo from cluster record)
    │              5. Creates ArgoCD Application pointing to k8s/ path
    │
    └─► UpdateStatusReady (DynamoDB: status=READY, step=COMPLETE, argocd_url=...)
```

Flutter app auto-polls `GET /clusters/{cluster_id}` every 10 seconds and advances the progress stepper in real time.

---

## Workflow 3 — AI Code Analysis & Instrumentation

This workflow is triggered from the Co-Pilot screen or a dedicated "Analyze Repo" button on the cluster detail screen, once the cluster is READY.

### Input

- User's GitHub repo URL (read from `custom:github_token` secret + connected repo)
- Target cluster (for generating manifests scoped to that cluster's region/name)

### Sequence

```
Flutter App
    │  POST /agent/chat { message: "Analyze my repo and set up observability", session_id }
    ▼
agent_proxy Lambda → Bedrock Agent (Claude 3 Sonnet)
    │
    ▼
Bedrock Agent — Code Analysis Action Group
    │
    ├─► Tool: fetch_repo_tree
    │       Fetches GitHub file tree via GitHub API using stored OAuth2 token.
    │       Returns: file paths, languages detected, directory structure.
    │
    ├─► Tool: fetch_file_contents (called iteratively for key files)
    │       Fetches source files: entry points, service handlers, DB clients,
    │       HTTP clients, background workers, config files (package.json,
    │       requirements.txt, go.mod, pom.xml, etc.)
    │
    ├─► Agent reasoning pass (Claude 3 Sonnet):
    │       - Identifies: runtime (Node, Python, Go, Java, etc.), framework
    │         (Express, FastAPI, Gin, Spring, etc.), services, endpoints
    │       - Identifies: logging gaps, missing error handling, retry blocks,
    │         DB calls without tracing, async jobs without spans
    │       - Plans: which OTel SDK/auto-instrumentation package is appropriate
    │         for the detected stack
    │
    ├─► Tool: generate_instrumented_files
    │       Returns a set of file patches/additions:
    │       ┌─────────────────────────────────────────────────────────┐
    │       │ 1. OTel SDK setup file (e.g. tracing.js / tracer.py)    │
    │       │    - Configures TracerProvider, resource attributes,     │
    │       │      OTLP exporter pointed at the collector sidecar      │
    │       │ 2. Auto-instrumentation bootstrap                        │
    │       │    - e.g. require('./tracing') at top of entry point     │
    │       │    - or opentelemetry-instrument for Python              │
    │       │ 3. Manual span injections (patch hunks) for:            │
    │       │    - Identified business-critical functions              │
    │       │    - DB/cache calls                                      │
    │       │    - External HTTP calls                                 │
    │       │    - Async/queue consumers                               │
    │       │ 4. Structured log additions (using existing logger or    │
    │       │    stdlib, enriched with trace_id/span_id correlation)   │
    │       │ 5. Custom metrics (counters, histograms) at:             │
    │       │    - Request handlers (latency histogram)                │
    │       │    - Error paths (error counter)                         │
    │       │    - Any identified business KPIs (e.g. order_placed)   │
    │       └─────────────────────────────────────────────────────────┘
    │
    ├─► Tool: generate_dockerfile
    │       Produces a multi-stage Dockerfile appropriate for the runtime.
    │       Includes the OTel collector as a sidecar (or recommends ADOT).
    │
    ├─► Tool: generate_k8s_manifests
    │       Produces files to be placed in the ops repo under k8s/:
    │       - deployment.yaml (image placeholder, resource requests, OTel env vars)
    │       - service.yaml
    │       - hpa.yaml
    │       - configmap.yaml (OTel collector config if sidecar pattern used)
    │       - ingress.yaml (optional, if HTTP service detected)
    │
    └─► Agent returns a structured response to the user in Co-Pilot chat:
            - Summary of what was found and instrumented
            - List of files changed + why
            - Dockerfile
            - K8s manifests
            - Instructions: "Commit these files to your ops repo under k8s/ and
              push — ArgoCD will automatically detect and deploy."
```

> **Note on ops repo creation:** If the user hasn't yet created their ops repo, the agent provides step-by-step instructions:
> 1. Go to github.com → New Repository → name it `<cluster-name>-ops` → Private → no README.
> 2. Clone it locally → create a `k8s/` directory.
> 3. Paste the generated manifests into `k8s/`.
> 4. `git push origin main`.
> 5. Paste the repo URL into the Provision Cluster form.

---

## Workflow 4 — Continuous Cluster Health Monitoring

### Architecture: Hybrid EventBridge + Bedrock Agent

The monitoring system has two modes:

#### Mode A — Scheduled Proactive Health Checks (EventBridge)

```
EventBridge Scheduler
    │  Rate: every 5 minutes
    ▼
health_monitor Lambda (new Lambda, not in current spec — add to spec)
    │
    ├─► Scans DynamoDB clusters table for all clusters with status=READY
    │
    ├─► For each cluster:
    │       1. Assumes Strata-platform-reader in customer account (using external_id)
    │       2. Calls eks:DescribeCluster → checks cluster status
    │       3. Calls CloudWatch GetMetricStatistics for:
    │              - node_cpu_utilization > 80% threshold
    │              - node_memory_utilization > 85% threshold
    │              - pod restart counts > threshold
    │       4. Calls CloudWatch Logs FilterLogEvents for ERROR patterns in
    │          last 5 minutes across /aws/eks/{cluster_id}/cluster log group
    │
    ├─► If anomaly detected:
    │       1. Writes alert record to DynamoDB `alerts` table:
    │              { user_id, cluster_id, alert_type, severity, message, timestamp }
    │       2. Triggers SNS → Firebase/APNs push notification to the Flutter app:
    │              "⚠ PROD-NORTH-01: CPU at 87% — tap to view details"
    │       3. (Optional v2) Invokes Bedrock Agent in background to generate
    │          a suggested fix, stored alongside the alert record.
    │
    └─► Flutter app: Dashboard "Recent Activities" feed polls GET /alerts (new endpoint)
        and displays new entries in real time.
```

#### Mode B — On-Demand Agent Queries (Co-Pilot)

```
User types in Co-Pilot:
  "What's the CPU usage on PROD-NORTH-01?"
  "Are there any error spikes in the last hour?"
  "Why did my pod crash?"
         │
         ▼
agent_proxy Lambda → Bedrock Agent
         │
         ├─► Bedrock Agent calls agent_tools Lambda with appropriate api_path:
         │       /health, /pods, /logs, /metrics
         │
         ├─► agent_tools Lambda assumes strata-platform-reader,
         │   queries EKS/CloudWatch in real time
         │
         └─► Bedrock Agent synthesizes a natural-language response back to the user
             (with structured data cards rendered in Flutter)
```

### DynamoDB `alerts` Table (new)

| Attribute | Type | Notes |
|-----------|------|-------|
| `user_id` | PK String | Cognito `sub` |
| `alert_id` | SK String | `alert-{uuid}` |
| `cluster_id` | String | FK to clusters table |
| `alert_type` | String | `CPU_HIGH \| MEMORY_HIGH \| POD_CRASH \| CLUSTER_UNHEALTHY \| LOG_ERROR_SPIKE` |
| `severity` | String | `INFO \| WARNING \| CRITICAL` |
| `message` | String | Human-readable description |
| `raw_data` | Map | Raw metric values that triggered the alert |
| `suggested_fix` | String | Bedrock-generated suggestion (optional, populated async) |
| `acknowledged` | Boolean | User dismissed in app |
| `created_at` | String | ISO 8601 |
| `expires_at` | Number | TTL — alerts expire after 7 days |

---

## Workflow 5 — Cluster Deprovisioning

### Trigger

User taps **"Delete Cluster"** on Cluster Detail screen → confirmation dialog → `DELETE /clusters/{cluster_id}`.

### Sequence

```
orchestrator Lambda
    │  1. Updates DynamoDB: status=DELETING, step=DELETE_STARTED
    │  2. Starts Step Functions deprovision_cluster execution
    ▼
Step Functions — deprovision_cluster.asl.json
    │
    ├─► UpdateStatusDeleting (DynamoDB)
    │
    ├─► RunTerraformDestroy
    │       └─ StartCodeBuild Lambda (waitForTaskToken) runs terraform destroy
    │          in customer account using strata-platform-provisioner role
    │
    ├─► CleanupArgoCD (optional — delete ArgoCD Application record)
    │
    └─► UpdateStatusDeleted
            └─ DynamoDB: status=DELETED
            └─ TTL field set to now+1hour (record auto-deleted)
```

---

## Workflow 6 — GitHub Token Refresh

GitHub OAuth2 tokens do not expire unless revoked, but if the user disconnects and reconnects:

1. User navigates to Settings → "Reconnect GitHub".
2. Same OAuth2 flow as onboarding Step 2.
3. New token overwrites the existing secret in Secrets Manager.
4. Cognito attribute `custom:github_connected` remains `true`.

---

## Key Design Decisions (Reference)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| GitHub integration | OAuth2 (not OIDC) | OIDC is for machine-to-machine; OAuth2 is correct for user-facing token grant |
| `external_id` generation | At signup, stored per-user in DynamoDB | Generated early for CFN link injection; per-user prevents confused deputy attacks |
| CloudFormation URL generation | Dedicated `onboarding` Lambda | Fetches `external_id` from DDB, injects it as CFN parameter, generates pre-signed S3 URL |
| Ops repo creation | Agent generates instructions only | Avoids granting the platform write access to the user's GitHub org |
| Which repo ArgoCD uses | The ops repo created from agent instructions | User provides URL at cluster provision time; ArgoCD tracks `k8s/` path |
| Monitoring trigger | EventBridge (scheduled) + Co-Pilot (on-demand) | Proactive alerting via EventBridge; reactive deep queries via Bedrock Agent |
| Code instrumentation depth | Full parse + auto + manual | Agent reads actual source to find instrumentation opportunities, not just template-applies |
