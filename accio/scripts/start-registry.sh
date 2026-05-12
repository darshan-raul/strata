#!/bin/bash
set -e

REGISTRY_NAME="accio-registry"
REGISTRY_PORT="5000"

echo "Starting local Docker registry for Accio..."

# Check if registry already exists
if docker ps | grep -q "$REGISTRY_NAME"; then
    echo "Registry already running"
else
    docker run -d --restart=always \
        -p ${REGISTRY_PORT}:5000 \
        --name "$REGISTRY_NAME" \
        registry:2
    echo "Registry started on localhost:${REGISTRY_PORT}"
fi

# Configure Kind to use the registry
if kind get clusters | grep -q "^accio$"; then
    echo "Kind cluster 'accio' already exists"
else
    echo "Creating Kind cluster with registry configuration..."
    kind create cluster --config accio-kind.yaml
fi

# Patch the node to use registry config
kubectl patch node accio-control-plane -p '{"imagePullOverrides":{}}' 2>/dev/null || true

echo ""
echo "Registry ready at localhost:${REGISTRY_PORT}"
echo "Run 'tilt up' to start developing"