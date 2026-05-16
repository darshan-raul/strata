# Accio Kubernetes Setup for Kind v1.36

This guide walks through deploying the Accio application suite on a Kind (Kubernetes in Docker) cluster v1.36.

## Prerequisites

- Docker installed and running
- kubectl installed
- Kind v0.24+ installed
- At least 4GB RAM available for the cluster

## Step 1: Create Kind Cluster

Create a Kind cluster with extra port mappings for the services and local registry configuration:

```bash
cat > accio-kind.yaml << 'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: accio
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30000
    hostPort: 3000
    protocol: TCP
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      imageRepository: localhost:5000
      imagePullPolicy: IfNotPresent
```

```bash
kind create cluster --config accio-kind.yaml --image kindest/node:v1.36.0
```

## Development with Tilt (Recommended)

Tilt automates the build→push→deploy cycle with file watching. Install once with:
```bash
brew install tilt  # macOS
# or: curl -fsSL https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/get_tilt.sh | bash
```

**First-time setup:**
```bash
bash scripts/start-registry.sh  # starts registry + creates cluster with registry config
```

**Every development session:**
```bash
tilt up
```

Tilt will:
- Watch for code changes and rebuild automatically
- Push images to local registry (`localhost:5000`)
- Deploy updates to Kind cluster
- Show live logs in web UI at `localhost:10350`

**Cleanup:**
```bash
tilt down  # removes deployed resources (keeps cluster)
```

---

## Manual Approach (Original)

### Step 2: Build and Push Images to Local Registry

```bash
# Start local registry if not running
docker run -d --restart=always -p 5000:5000 --name accio-registry registry:2

# Build and push each service
for svc in auth-service catalog-service provisioner-service scorecard-service workflow-engine audit-service portal-ui; do
  docker build -t localhost:5000/$svc:latest ./services/$svc
  docker push localhost:5000/$svc:latest
done
```

### Step 3: Deploy to Kubernetes

```bash
kind load docker-image auth-service:latest --name accio
kind load docker-image catalog-service:latest --name accio
kind load docker-image provisioner-service:latest --name accio
kind load docker-image scorecard-service:latest --name accio
kind load docker-image workflow-engine:latest --name accio
kind load docker-image audit-service:latest --name accio
kind load docker-image portal-ui:latest --name accio
```

## Step 4: Deploy to Kubernetes

Apply the manifests in order:

```bash
# 1. Infrastructure (PostgreSQL, ConfigMaps, Secrets)
kubectl apply -f k8s/base/infrastructure.yaml

# Wait for postgres to be ready
kubectl wait --for=condition=available --timeout=120s deployment/postgres -n accio

# 2. Deploy auth-service
kubectl apply -f k8s/base/services/auth-service.yaml

# 3. Microservices
kubectl apply -f k8s/base/services/catalog-service.yaml
kubectl apply -f k8s/base/services/provisioner-service.yaml
kubectl apply -f k8s/base/services/scorecard-service.yaml
kubectl apply -f k8s/base/services/workflow-service.yaml
kubectl apply -f k8s/base/services/audit-service.yaml

# 4. Portal UI
kubectl apply -f k8s/base/services/portal-ui.yaml
```

Or apply all at once:

```bash
kubectl apply -f k8s/base/
```

## Step 5: Verify Deployment

Check that all pods are running:

```bash
kubectl get pods -n accio
```

Expected output:
```
NAME                                READY   STATUS    RESTARTS   AGE
postgres-xxxxx                      1/1     Running   0          1m
redis-xxxxx                        1/1     Running   0          1m
nats-xxxxx                          1/1     Running   0          1m
auth-service-xxxxx                  1/1     Running   0          1m
catalog-service-xxxxx               1/1     Running   0          1m
provisioner-service-xxxxx           1/1     Running   0          1m
scorecard-service-xxxxx             1/1     Running   0          1m
workflow-engine-xxxxx               1/1     Running   0          1m
audit-service-xxxxx                 1/1     Running   0          1m
portal-ui-xxxxx                     1/1     Running   0          1m
```

## Step 6: Access Services

| Service        | URL                                    | Kind Port |
|----------------|----------------------------------------|-----------|
| Portal UI      | http://accio.localhost:3000            | 30000     |
| Catalog API    | http://localhost:8081 (via port-forward) | -       |
| Provisioner    | http://localhost:8082 (via port-forward) | -       |
| Scorecard      | http://localhost:8083 (via port-forward) | -       |
| Workflow       | http://localhost:8084 (via port-forward) | -       |
| Audit          | http://localhost:8085 (via port-forward) | -       |

## Step 7: Add Local DNS Entry (Optional)

Add to your `/etc/hosts`:
```
127.0.0.1 accio.localhost
```

## Step 8: Port Forwards for Backend APIs

```bash
# Auth Service
kubectl port-forward -n accio svc/auth-service 8086:8086

# Catalog Service
kubectl port-forward -n accio svc/catalog-service 8081:8081

# Provisioner Service
kubectl port-forward -n accio svc/provisioner-service 8082:8082

# Scorecard Service
kubectl port-forward -n accio svc/scorecard-service 8083:8083

# Workflow Engine
kubectl port-forward -n accio svc/workflow-engine 8084:8084

# Audit Service
kubectl port-forward -n accio svc/audit-service 8085:8085
```

## Authentication

Default test users (hardcoded for POC):

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | admin |
| dev | dev123 | developer |
| ops | ops123 | operator |
| test | test123 | developer |

## Cleanup

```bash
# Delete the cluster
kind delete cluster --name accio

# Or just delete the namespace
kubectl delete namespace accio
```

## Troubleshooting

### Images Not Loading
If pods are in `ImagePullBackOff`, ensure images are loaded:
```bash
kind get nodes -n accio
docker exec -it accio-control-plane crictl images
```

### PostgreSQL Not Starting
Check init logs:
```bash
kubectl logs -n accio deployment/postgres
```

## Architecture Notes

- **Namespace**: `accio`
- **Service Discovery**: Kubernetes DNS (e.g., `http://catalog-service:8081`)
- **Database**: PostgreSQL with init script mounted via ConfigMap
- **Cache**: Redis for workflow engine
- **Messaging**: NATS JetStream
- **Auth**: Simple JWT-based auth service (auth-service) with hardcoded users for POC