# Strata Platform — Sequence Diagrams

---

## Workflow 1 — Initial Onboarding

### 1a. Sign Up & external_id Generation

```mermaid
sequenceDiagram
    actor User
    participant App as Flutter App
    participant Cognito
    participant OrchestratorLambda as orchestrator Lambda
    participant DDB as DynamoDB (users)

    User->>App: Enter email + password
    App->>Cognito: signUp(email, password)
    Cognito-->>App: SUCCESS — verification email sent
    App->>User: Show "Enter verification code" screen
    User->>App: Enter code
    App->>Cognito: confirmSignUp(code)
    Cognito-->>App: User confirmed

    App->>OrchestratorLambda: POST /users/me/init (Cognito JWT)
    OrchestratorLambda->>OrchestratorLambda: Generate external_id (UUID v4)
    OrchestratorLambda->>DDB: PutItem { user_id, external_id, created_at }
    OrchestratorLambda->>Cognito: UpdateUserAttributes(custom:external_id)
    OrchestratorLambda-->>App: 200 OK
    App->>User: Navigate to "Connect GitHub" screen
```

---

### 1b. GitHub OAuth2 Connection

```mermaid
sequenceDiagram
    actor User
    participant App as Flutter App
    participant GitHub
    participant APIGW as API Gateway
    participant OrchestratorLambda as orchestrator Lambda
    participant SM as Secrets Manager
    participant Cognito

    User->>App: Tap "Connect GitHub Account"
    App->>GitHub: Open WebView — OAuth2 authorize URL (scope: repo, read:user)
    GitHub->>User: Show permissions consent screen
    User->>GitHub: Authorize
    GitHub-->>App: Redirect to Strata://callback?code=XYZ&state=ABC

    App->>App: Validate state (CSRF check)
    App->>APIGW: PUT /users/me/github-token { code }
    APIGW->>OrchestratorLambda: Invoke
    OrchestratorLambda->>GitHub: POST /login/oauth/access_token { code }
    GitHub-->>OrchestratorLambda: { access_token }
    OrchestratorLambda->>SM: PutSecretValue Strata/users/{user_id}/github
    OrchestratorLambda->>Cognito: UpdateUserAttributes(custom:github_connected=true)
    OrchestratorLambda-->>App: 200 { status: "ok" }
    App->>User: Navigate to "Cloud Credentials" screen
```

---

### 1c. AWS IAM Setup via CloudFormation

```mermaid
sequenceDiagram
    actor User
    participant App as Flutter App
    participant APIGW as API Gateway
    participant OnboardingLambda as onboarding Lambda
    participant DDB as DynamoDB (users)
    participant S3
    participant AWSConsole as AWS Console (Customer Browser)
    participant CustomerAccount as Customer AWS Account
    participant Cognito

    User->>App: Enter 12-digit AWS Account ID
    User->>App: Tap "Generate Setup Link"
    App->>APIGW: GET /onboarding/cloudformation-url?account_id=123456789012
    APIGW->>OnboardingLambda: Invoke
    OnboardingLambda->>DDB: GetItem { user_id } — fetch external_id
    OnboardingLambda->>S3: GeneratePresignedUrl(onboarding_cfn.yaml, TTL=1h)
    OnboardingLambda-->>App: { cloudformation_url, external_id }

    App->>User: Show step-by-step guidance panel + deep-link button
    User->>AWSConsole: Open CloudFormation deep-link in browser
    Note over AWSConsole: Pre-filled params: StrataAccountId, ExternalId

    User->>AWSConsole: Check IAM acknowledgement + Create Stack
    AWSConsole->>CustomerAccount: Create Strata-platform-provisioner role
    AWSConsole->>CustomerAccount: Create Strata-platform-reader role
    Note over CustomerAccount: Both roles have trust policy scoped to ExternalId
    CustomerAccount-->>AWSConsole: Stack CREATE_COMPLETE

    User->>App: Tap "Verify Setup"
    App->>APIGW: GET /onboarding/verify-iam?account_id=123456789012
    APIGW->>OnboardingLambda: Invoke
    OnboardingLambda->>DDB: GetItem { user_id } — fetch external_id
    OnboardingLambda->>CustomerAccount: sts:AssumeRole(Strata-platform-reader, ExternalId)
    CustomerAccount-->>OnboardingLambda: Temporary credentials
    OnboardingLambda-->>App: { verified: true }

    App->>Cognito: UpdateUserAttributes(custom:aws_account_id)
    App->>DDB: Update users item { aws_account_id }
    App->>User: Navigate to Dashboard
```

---

## Workflow 2 — Cluster Provisioning

```mermaid
sequenceDiagram
    actor User
    participant App as Flutter App
    participant APIGW as API Gateway
    participant OrchestratorLambda as orchestrator Lambda
    participant DDB as DynamoDB (clusters)
    participant SFN as Step Functions
    participant StartCBLambda as StartCodeBuild Lambda
    participant CodeBuild
    participant CustomerEKS as Customer AWS (EKS + VPC)
    participant StatusChecker as status_checker Lambda
    participant ArgoCDDeployer as argocd_deployer Lambda
    participant SM as Secrets Manager
    participant ArgoCD

    User->>App: Fill Provision form (name, region, instance_type, ops_repo_url)
    User->>App: Tap "LAUNCH CLUSTER"
    App->>User: Confirmation dialog
    User->>App: Confirm

    App->>APIGW: POST /clusters { name, provider, region, instance_type, github_repo }
    APIGW->>OrchestratorLambda: Invoke (JWT: user_id, aws_account_id)
    OrchestratorLambda->>OrchestratorLambda: Generate cluster_id
    OrchestratorLambda->>DDB: PutItem { status=INITIATED, step=STARTED }
    OrchestratorLambda->>SFN: StartExecution(provision_cluster)
    OrchestratorLambda-->>App: 202 { cluster_id, status: INITIATED }
    App->>App: Start polling GET /clusters/{cluster_id} every 10s

    SFN->>DDB: UpdateItem { status=PROVISIONING, step=TERRAFORM_APPLY }

    SFN->>StartCBLambda: Invoke with waitForTaskToken
    StartCBLambda->>CodeBuild: StartBuild(cluster_id, region, aws_account_id, external_id)
    CodeBuild->>CustomerEKS: AssumeRole(Strata-platform-provisioner, ExternalId)
    CodeBuild->>CustomerEKS: terraform apply (VPC + EKS + ArgoCD Helm)
    CustomerEKS-->>CodeBuild: cluster_endpoint, argocd_url, argocd_admin_password
    CodeBuild->>StartCBLambda: SendTaskSuccess(task_token, terraform_output)
    StartCBLambda-->>SFN: terraform_output

    SFN->>DDB: UpdateItem { status=VALIDATING, step=CLUSTER_HEALTH_CHECK, cluster_endpoint }

    SFN->>StatusChecker: Invoke
    StatusChecker->>CustomerEKS: AssumeRole(Strata-platform-reader, ExternalId)
    StatusChecker->>CustomerEKS: eks:DescribeCluster
    CustomerEKS-->>StatusChecker: { status: ACTIVE }
    StatusChecker-->>SFN: validation passed

    SFN->>DDB: UpdateItem { status=INSTALLING_ARGOCD, step=HELM_ARGOCD }

    SFN->>ArgoCDDeployer: Invoke
    ArgoCDDeployer->>SM: GetSecretValue(Strata/users/{user_id}/github)
    SM-->>ArgoCDDeployer: { github_token }
    ArgoCDDeployer->>ArgoCD: GET /healthz (retry until ready)
    ArgoCDDeployer->>ArgoCD: POST /api/v1/session — get bearer token
    ArgoCDDeployer->>ArgoCD: POST /api/v1/repositories { repo, github_token }
    ArgoCDDeployer->>ArgoCD: POST /api/v1/applications { source: k8s/, syncPolicy: automated }
    ArgoCDDeployer-->>SFN: { argocd_url }

    SFN->>DDB: UpdateItem { status=READY, step=COMPLETE, argocd_url }
    App->>APIGW: GET /clusters/{cluster_id}
    APIGW-->>App: { status: READY, cluster_endpoint, argocd_url }
    App->>User: Show READY state + endpoint links
```

---

## Workflow 3 — AI Code Analysis & Instrumentation

```mermaid
sequenceDiagram
    actor User
    participant App as Flutter App (Co-Pilot)
    participant APIGW as API Gateway
    participant AgentProxy as agent_proxy Lambda
    participant Bedrock as Bedrock Agent (Claude 3 Sonnet)
    participant AgentTools as agent_tools Lambda
    participant GitHub
    participant SM as Secrets Manager

    User->>App: "Analyze my repo and set up observability"
    App->>APIGW: POST /agent/chat { message, session_id }
    APIGW->>AgentProxy: Invoke
    AgentProxy->>Bedrock: InvokeAgent(inputText, sessionId)

    Bedrock->>AgentTools: Tool — fetch_repo_tree
    AgentTools->>SM: GetSecretValue(github token)
    AgentTools->>GitHub: GET /repos/{owner}/{repo}/git/trees?recursive=1
    GitHub-->>AgentTools: File tree + language stats
    AgentTools-->>Bedrock: { file_tree, detected_languages }

    loop For each key source file
        Bedrock->>AgentTools: Tool — fetch_file_contents(path)
        AgentTools->>GitHub: GET /repos/{owner}/{repo}/contents/{path}
        GitHub-->>AgentTools: File content
        AgentTools-->>Bedrock: Decoded source code
    end

    Note over Bedrock: Reasoning pass: identify runtime + framework,\nmap services + endpoints, find logging gaps,\nmissing traces, metric opportunities

    Bedrock->>AgentTools: Tool — generate_instrumented_files { analysis }
    AgentTools->>AgentTools: Generate OTel setup file (TracerProvider + OTLP exporter)
    AgentTools->>AgentTools: Generate auto-instrumentation bootstrap
    AgentTools->>AgentTools: Generate manual span patch hunks (DB, HTTP, async)
    AgentTools->>AgentTools: Add structured logs (enriched with trace_id/span_id)
    AgentTools->>AgentTools: Add custom metrics (latency, error counters, KPIs)
    AgentTools->>AgentTools: Generate Dockerfile (multi-stage)
    AgentTools->>AgentTools: Generate k8s/ manifests (Deployment, Service, HPA, ConfigMap)
    AgentTools-->>Bedrock: All generated files + patch hunks

    Bedrock-->>AgentProxy: Structured response (summary, file list, ops repo instructions)
    AgentProxy-->>App: { reply, session_id }
    App->>User: Render in Co-Pilot (diffs, Dockerfile, manifests, setup guide)
    Note over User,App: User commits files to ops repo — ArgoCD auto-syncs
```

---

## Workflow 4 — Continuous Health Monitoring

### 4a. Scheduled Proactive Checks (EventBridge)

```mermaid
sequenceDiagram
    participant EB as EventBridge Scheduler (every 5 min)
    participant HealthMonitor as health_monitor Lambda
    participant DDB as DynamoDB (clusters + alerts)
    participant CustomerAccount as Customer AWS (EKS + CloudWatch)
    participant SNS
    participant App as Flutter App
    participant Bedrock as Bedrock Agent (async)

    EB->>HealthMonitor: Scheduled trigger
    HealthMonitor->>DDB: Scan clusters { status = READY }
    DDB-->>HealthMonitor: List of active clusters

    loop For each READY cluster
        HealthMonitor->>CustomerAccount: AssumeRole(Strata-platform-reader, ExternalId)
        HealthMonitor->>CustomerAccount: eks:DescribeCluster
        HealthMonitor->>CustomerAccount: CloudWatch GetMetricStatistics (cpu, memory)
        HealthMonitor->>CustomerAccount: CloudWatch FilterLogEvents (ERROR, last 5 min)
        CustomerAccount-->>HealthMonitor: Metrics + log events

        alt Anomaly detected
            HealthMonitor->>DDB: PutItem alerts { alert_type, severity, message, raw_data }
            HealthMonitor->>SNS: Publish push notification
            SNS-->>App: Firebase / APNs push — "CPU at 87% on PROD-NORTH-01"
            App->>App: Show alert banner on Dashboard
            HealthMonitor->>Bedrock: InvokeAgent async — generate suggested fix
            Bedrock-->>HealthMonitor: suggested_fix text
            HealthMonitor->>DDB: UpdateItem alert { suggested_fix }
        end
    end
```

---

### 4b. On-Demand Co-Pilot Health Queries

```mermaid
sequenceDiagram
    actor User
    participant App as Flutter App (Co-Pilot)
    participant APIGW as API Gateway
    participant AgentProxy as agent_proxy Lambda
    participant Bedrock as Bedrock Agent (Claude 3 Sonnet)
    participant AgentTools as agent_tools Lambda
    participant CustomerAccount as Customer AWS (EKS + CloudWatch)

    User->>App: "Why did my pod crash on PROD-NORTH-01?"
    App->>APIGW: POST /agent/chat { message, session_id, cluster_id }
    APIGW->>AgentProxy: Invoke
    AgentProxy->>Bedrock: InvokeAgent("[cluster_id=eks-abc-123] Why did my pod crash?")

    Bedrock->>AgentTools: Tool — /logs { cluster_id }
    AgentTools->>CustomerAccount: AssumeRole(Strata-platform-reader, ExternalId)
    AgentTools->>CustomerAccount: CloudWatch FilterLogEvents (ERROR, last 12h)
    CustomerAccount-->>AgentTools: Error log events
    AgentTools-->>Bedrock: { logs }

    Bedrock->>AgentTools: Tool — /pods { cluster_id }
    AgentTools->>CustomerAccount: EKS token auth — k8s CoreV1Api list_namespaced_pod
    CustomerAccount-->>AgentTools: Pod list + statuses
    AgentTools-->>Bedrock: { pods }

    Note over Bedrock: Synthesize: "payments-api crashed — OOMKilled.\n3 restarts. Fix: increase memory limit to 512Mi."

    Bedrock-->>AgentProxy: Completion stream
    AgentProxy-->>App: { reply, session_id }
    App->>User: Render structured response (log table + manifest patch suggestion)
```

---

## Workflow 5 — Cluster Deprovisioning

```mermaid
sequenceDiagram
    actor User
    participant App as Flutter App
    participant APIGW as API Gateway
    participant OrchestratorLambda as orchestrator Lambda
    participant DDB as DynamoDB (clusters)
    participant SFN as Step Functions
    participant StartCBLambda as StartCodeBuild Lambda
    participant CodeBuild
    participant CustomerAccount as Customer AWS Account

    User->>App: Tap "Delete Cluster"
    App->>User: Confirmation dialog
    User->>App: Confirm

    App->>APIGW: DELETE /clusters/{cluster_id}
    APIGW->>OrchestratorLambda: Invoke
    OrchestratorLambda->>DDB: UpdateItem { status=DELETING, step=DELETE_STARTED }
    OrchestratorLambda->>SFN: StartExecution(deprovision_cluster)
    OrchestratorLambda-->>App: 202 { status: DELETING }

    SFN->>DDB: UpdateItem { step=TERRAFORM_DESTROY }

    SFN->>StartCBLambda: Invoke with waitForTaskToken
    StartCBLambda->>CodeBuild: StartBuild(action=destroy, cluster vars)
    CodeBuild->>CustomerAccount: AssumeRole(Strata-platform-provisioner, ExternalId)
    CodeBuild->>CustomerAccount: terraform destroy (EKS + VPC + all resources)
    CustomerAccount-->>CodeBuild: Destroy complete
    CodeBuild->>StartCBLambda: SendTaskSuccess(task_token)
    StartCBLambda-->>SFN: done

    SFN->>DDB: UpdateItem { status=DELETED, expires_at=now+1h }
    Note over DDB: TTL auto-deletes record within 1 hour

    App->>APIGW: GET /clusters/{cluster_id}
    APIGW-->>App: { status: DELETED }
    App->>User: Remove cluster from list
```
