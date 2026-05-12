# Accio Kubernetes Setup for Kind v1.36

This guide walks through deploying the Accio application suite on a Kind (Kubernetes in Docker) cluster v1.36.

## Prerequisites

- Docker installed and running
- kubectl installed
- Kind v0.24+ installed
- At least 4GB RAM available for the cluster

## Step 1: Create Kind Cluster

Create a Kind cluster with extra port mappings for the services:

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
  - containerPort: 30991
    hostPort: 9091
    protocol: TCP
```

```bash
kind create cluster --config accio-kind.yaml --image kindest/node:v1.36.0
```

## Step 2: Build Docker Images

Build all service images and load them into the Kind cluster:

```bash
# Build catalog-service
docker build -t catalog-service:latest ./services/catalog-service

# Build provisioner-service
docker build -t provisioner-service:latest ./services/provisioner-service

# Build scorecard-service
docker build -t scorecard-service:latest ./services/scorecard-service

# Build workflow-engine
docker build -t workflow-engine:latest ./services/workflow-engine

# Build audit-service
docker build -t audit-service:latest ./services/audit-service

# Build portal-ui
docker build -t portal-ui:latest ./services/portal-ui
```

## Step 3: Load Images into Kind

```bash
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
kubectl apply -f k8s/00-infrastructure.yaml

# Wait for postgres to be ready
kubectl wait --for=condition=available --timeout=120s deployment/postgres -n accio

# 2. Redis
kubectl apply -f k8s/01-redis.yaml

# 3. NATS
kubectl apply -f k8s/02-nats.yaml

# 4. Authelia
kubectl apply -f k8s/03-authelia.yaml

# 5. Microservices
kubectl apply -f k8s/04-catalog-service.yaml
kubectl apply -f k8s/05-provisioner-service.yaml
kubectl apply -f k8s/06-scorecard-service.yaml
kubectl apply -f k8s/07-workflow-engine.yaml
kubectl apply -f k8s/08-audit-service.yaml

# 6. Portal UI
kubectl apply -f k8s/09-portal-ui.yaml
```

Or apply all at once:

```bash
kubectl apply -f k8s/
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
authelia-xxxxx                     1/1     Running   0          1m
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
| Authelia       | http://accio.localhost:9091            | 30991     |
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

Default test user:
- Username: `admin`
- Password: `admin`
- (Hashed in users.yml - the plaintext password is `admin`)

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

### Authelia Issues
The ConfigMap contains inline configuration. For production, consider using proper secrets management.

## Architecture Notes

- **Namespace**: `accio`
- **Service Discovery**: Kubernetes DNS (e.g., `http://catalog-service:8081`)
- **Database**: PostgreSQL with init script mounted via ConfigMap
- **Cache**: Redis for workflow engine
- **Messaging**: NATS JetStream
- **Auth**: Authelia OIDC for portal SSO