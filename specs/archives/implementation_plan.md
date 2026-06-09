# Strata Platform — Staged Build Plan

## Philosophy

Build **vertically** (thin slices that are fully testable end-to-end) rather than **horizontally** (all infra first, then all lambdas, etc.). Each stage produces something you can actually run and verify before moving to the next.

Dependency order is strict: infra → lambdas → state machines → Flutter UI.  
The Bedrock Agent is intentionally last — it depends on everything else being live.

---

## Stage 1 — Platform Foundation (Infra skeleton)

> **Goal:** Strata AWS account has all always-on resources. Nothing provisioned in customer accounts yet.

### Files
- `infra/main.tf` — provider, backend, data sources
- `infra/cognito.tf` — User Pool, App Client, custom attributes (`github_token`, `aws_account_id`)
- `infra/dynamodb.tf` — `clusters` table (PK `user_id`, SK `cluster_id`, TTL)
- `infra/s3.tf` — four S3 buckets (`Strata-tf-code`, `Strata-tf-state`, `Strata-outputs`, `Strata-agent-schemas`, `Strata-onboarding-cfn`)
- `infra/secrets_manager.tf` — KMS key + resource policy
- `infra/iam.tf` — Strata-side roles: `Strata-codebuild-role`, `Strata-lambda-role`
- `onboarding_cfn.yaml` — customer-side CloudFormation template (upload to `Strata-onboarding-cfn` bucket)

### Verification
```bash
terraform -chdir=infra apply
# Cognito pool exists, DynamoDB table exists, S3 buckets exist
aws cognito-idp describe-user-pool --user-pool-id <id>
aws dynamodb describe-table --table-name clusters
```

---

## Stage 2 — Core API Layer (Lambda + API Gateway)

> **Goal:** All REST endpoints are live. Can sign up, list clusters, post a cluster (it writes to DDB and stops — no SFN yet).

### Files
- `lambdas/orchestrator/handler.py` — POST /clusters, DELETE /clusters/{id}, PUT /users/me/github-token, GET /onboarding/cloudformation-url, GET /onboarding/verify-iam
- `lambdas/orchestrator/requirements.txt`
- `lambdas/status_checker/handler.py` — GET /dashboard/summary, GET /clusters (list)
- `lambdas/status_checker/requirements.txt`
- `infra/lambdas.tf` — zip + deploy both lambdas, env vars (`SFN_CREATE_ARN` left as placeholder for now), feature flags `ENABLE_AZURE=false`, `ENABLE_GCP=false`
- `infra/api_gateway.tf` — HTTP API, Cognito JWT authorizer, all 7 routes wired
- `GET /config` route — returns `{ "providers": ["aws"] }` (static Lambda or API GW mock)

### Verification
```bash
# Sign up via Cognito, get JWT, call API directly
curl -H "Authorization: Bearer $JWT" \
  https://<api-id>.execute-api.ap-south-1.amazonaws.com/prod/clusters
# → 200 []

curl -X POST -H "Authorization: Bearer $JWT" \
  -d '{"name":"test","provider":"aws","region":"ap-south-1","instance_type":"t3.medium"}' \
  .../prod/clusters
# → 202 { cluster_id: "eks-...", status: "INITIATED" }

aws dynamodb get-item --table-name clusters --key '...'
# → item exists with status=INITIATED
```

---

## Stage 3 — Provisioning Engine (CodeBuild + Step Functions)

> **Goal:** A cluster goes from INITIATED → READY (or FAILED) fully automatically.

### Files
- `lambdas/start_codebuild/handler.py` — the missing relay Lambda (calls `codebuild.start_build` with task token as env var)
- `lambdas/start_codebuild/requirements.txt`
- `buildspec.yml` — Terraform install, assume-role, init, apply/destroy, send-task-success/failure
- `state_machines/provision_cluster.asl.json` — full CREATE machine
- `state_machines/deprovision_cluster.asl.json` — DELETE mirror
- `infra/codebuild.tf` — CodeBuild project, env vars, IAM
- `infra/step_functions.tf` — both state machines, re-wire orchestrator's `SFN_CREATE_ARN` + `SFN_DELETE_ARN`
- `terraform/aws/` — VPC, EKS module, Helm ArgoCD, outputs

> [!IMPORTANT]  
> This stage is the longest. EKS cluster creation takes 12-15 minutes per test run. Budget time accordingly.

### Verification
```bash
# Trigger via API POST /clusters
# Watch Step Functions console → states advance
# After ~15 min: DDB item status = READY, cluster_endpoint populated
# kubectl get nodes using the endpoint in outputs
```

---

## Stage 4 — Cluster Reads & Status Checker

> **Goal:** `GET /clusters/{id}` returns live EKS status; dashboard summary counts are correct.

### Files
- `lambdas/status_checker/handler.py` — add `_assume_role` + EKS describe + CloudWatch metrics (already sketched in spec, complete the impl)
- Wire DynamoDB direct integration for `GET /clusters/{cluster_id}` in API GW (no Lambda hop)
- Wire `GET /clusters` (list) DynamoDB query via status_checker

### Verification
```bash
curl .../prod/clusters/eks-abc-123
# → { status: "READY", endpoint: "https://...", cpu: 12.4, ... }

curl .../prod/dashboard/summary
# → { total: 1, healthy: 1, unhealthy: 0 }
```

---

## Stage 5 — Flutter App: Onboarding

> **Goal:** A user can sign up, connect GitHub, deploy IAM roles, and land on the Dashboard — on both Android and Web.

### Files
- `flutter_app/pubspec.yaml` — dependencies: `amplify_flutter`, `amplify_auth_cognito`, `webview_flutter`, `http`, `flutter_secure_storage`
- `flutter_app/web/index.html` + `manifest.json`
- `flutter_app/lib/main.dart` — Amplify config, router boot
- `flutter_app/lib/theme/app_theme.dart` — dark navy theme, all colour tokens
- `flutter_app/lib/services/auth_service.dart` — Cognito signUp, confirmSignUp, signIn, getIdToken
- `flutter_app/lib/services/api_service.dart` — all endpoint wrappers
- `flutter_app/lib/services/github_service.dart` — OAuth webview + token PUT
- `flutter_app/lib/screens/onboarding/signup_screen.dart`
- `flutter_app/lib/screens/onboarding/github_connect_screen.dart`
- `flutter_app/lib/screens/onboarding/cloud_credentials_screen.dart`
  - AWS card: Account ID field, Generate Setup Link, 5-step guidance panel, Verify Setup button
  - Azure card: Coming Soon overlay + bottom-sheet
  - GCP card: Coming Soon overlay + bottom-sheet

### Verification
```
flutter run -d chrome        # web
flutter run -d <android-id>  # Android
# Full onboarding flow: sign up → verify email → GitHub OAuth → deploy CFN → verify IAM → Dashboard
```

---

## Stage 6 — Flutter App: Main Screens

> **Goal:** All three bottom-nav tabs are functional with live data.

### Files
- `flutter_app/lib/models/cluster.dart` + `chat_message.dart`
- `flutter_app/lib/widgets/cluster_card.dart`, `stat_card.dart`, `provider_selector.dart`, `activity_feed.dart`
- `flutter_app/lib/screens/dashboard_screen.dart` — stat cards, cluster list, recent activity, FAB
- `flutter_app/lib/screens/clusters_screen.dart` — cluster list with status badges
- `flutter_app/lib/screens/provision_screen.dart` — Cluster Name, Provider toggle (Azure/GCP disabled), Region dropdown, Instance Type, LAUNCH button + confirm dialog
- `flutter_app/lib/screens/cluster_detail_screen.dart` — progress stepper, 10s auto-poll, endpoint/ArgoCD links, delete button
- Bottom nav with 3 tabs (Dashboard / Clusters / Co-Pilot)

### Verification
```
# Provision a cluster from the app, watch stepper advance in real-time
# Delete the cluster, confirm it reaches DELETED status
```

---

## Stage 7 — Bedrock Co-Pilot

> **Goal:** Co-Pilot screen sends messages and gets intelligent responses about real cluster state.

### Files
- `lambdas/agent_tools/handler.py` — complete the EKS token auth, pods/services/health/logs paths (stubs already in spec)
- `lambdas/agent_tools/requirements.txt` — add `kubernetes`
- `lambdas/agent_proxy/handler.py` — Bedrock Agent runtime relay (already complete in spec)
- `infra/bedrock_agent.tf` — Agent, Alias, Action Group wiring, `agent_schemas/cluster-query.yaml` upload
- `infra/agent_prompt.txt` — system prompt
- `flutter_app/lib/screens/copilot_screen.dart` — chat UI, quick-action chips, session ID
- `flutter_app/lib/widgets/chat_bubble.dart`

> [!NOTE]  
> Bedrock model access must be enabled manually in the AWS console before `terraform apply` for this stage.

### Verification
```
# In Co-Pilot: "How many pods are running on eks-abc-123?"
# → Agent tool call → /pods → EKS → structured response rendered in chat
```

---

## Stage 8 — Hardening & Polish

> **Goal:** Production-ready. Error paths handled, web hosting live, security tightened.

### Tasks
- Replace `AdministratorAccess` on `Strata-platform-provisioner` with a scoped-down policy (EKS, EC2, VPC, IAM:PassRole only)
- Add `ExternalId` to all `sts:assume_role` calls in CodeBuild + Lambda (align with CFN template)
- CloudFront distribution in front of S3 web bucket (HTTPS, custom domain)
- Cognito hosted UI / SES email sender for verification emails
- API Gateway throttling + WAF basic rules
- Flutter error handling: network errors, token expiry refresh, empty states
- End-to-end smoke test script covering the full flow

---

## Dependency Graph

```
Stage 1 (Infra)
    │
    └── Stage 2 (API Layer)
            │
            └── Stage 3 (Provisioning Engine) ──┐
                    │                            │
                    └── Stage 4 (Status Reads)   │
                            │                    │
                            └── Stage 5 (Flutter Onboarding)
                                        │
                                        └── Stage 6 (Flutter Main Screens)
                                                    │
                                                    └── Stage 7 (Bedrock Co-Pilot)
                                                                │
                                                                └── Stage 8 (Hardening)
```

---

## Estimated effort per stage

| Stage | Complexity | Main risk |
|-------|-----------|-----------|
| 1 — Infra skeleton | Low | Terraform state bootstrap |
| 2 — API layer | Medium | Cognito JWT authorizer wiring |
| 3 — Provisioning engine | **High** | EKS creation time, task token relay, CodeBuild IAM |
| 4 — Status reads | Low | STS cross-account assume-role permissions |
| 5 — Flutter onboarding | Medium | Web OAuth webview (different on web vs Android) |
| 6 — Flutter main screens | Medium | Real-time polling UX, provider_selector state |
| 7 — Bedrock Co-Pilot | Medium | EKS token auth, Bedrock agent action group schema |
| 8 — Hardening | Low-Medium | IAM scoping, CloudFront config |
