SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

KIND_CLUSTER     := strata-dev
KIND_CONFIG      := strata-dev-kind.yaml
KUBE_CONTEXT     := kind-$(KIND_CLUSTER)
NAMESPACE        := strata
REGISTRY_NAME    := kind-registry
REGISTRY_PORT    := 5000
REGISTRY         := localhost:$(REGISTRY_PORT)
AGENT_IMAGE      := $(REGISTRY)/strata-agent-service:latest
AGENT_DIR        := services/agent-service
MANIFESTS_DIR    := control-plane/manifests
PORT_AGENT       := 8080
LITELLM_SECRET   := $(MANIFESTS_DIR)/10-litellm/secret.yaml

.DEFAULT_GOAL := help

.PHONY: help
help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Cluster lifecycle ──────────────────────────────────────────────

.PHONY: registry-up
registry-up: ## start the local docker registry (idempotent)
	@if [ -z "$$(docker ps -q -f name=$(REGISTRY_NAME))" ]; then \
		docker run -d --restart=always -p $(REGISTRY_PORT):5000 --name $(REGISTRY_NAME) registry:2 >/dev/null; \
		echo "started registry $(REGISTRY_NAME) on :$(REGISTRY_PORT)"; \
	else \
		echo "registry $(REGISTRY_NAME) already running"; \
	fi

.PHONY: registry-down
registry-down: ## stop the local docker registry
	-docker stop $(REGISTRY_NAME) >/dev/null 2>&1
	-docker rm   $(REGISTRY_NAME) >/dev/null 2>&1
	@echo "registry stopped"

.PHONY: kind-up
kind-up: registry-up ## create the kind cluster (or print a message if it already exists)
	@if [ -z "$$(kind get clusters 2>/dev/null | grep -E '^$(KIND_CLUSTER)$$')" ]; then \
		kind create cluster --config $(KIND_CONFIG) --image kindest/node:v1.29.0; \
		docker network connect kind $(REGISTRY_NAME) 2>/dev/null || true; \
		echo "cluster $(KIND_CLUSTER) created"; \
	else \
		echo "cluster $(KIND_CLUSTER) already exists"; \
	fi

.PHONY: kind-down
kind-down: ## delete the kind cluster (keeps the registry)
	-kind delete cluster --name $(KIND_CLUSTER)
	@echo "cluster $(KIND_CLUSTER) deleted"

.PHONY: kind-status
kind-status: ## show cluster + node status
	@kubectl --context $(KUBE_CONTEXT) get nodes -o wide
	@echo "---"
	@kubectl --context $(KUBE_CONTEXT) get pods -n $(NAMESPACE)

# ── Build ──────────────────────────────────────────────────────────

.PHONY: build
build: build-agent ## build all images and push to the local registry

.PHONY: build-agent
build-agent: ## build the agent-service image
	cd $(AGENT_DIR) && docker build -t $(AGENT_IMAGE) .
	docker push $(AGENT_IMAGE)
	@echo "pushed $(AGENT_IMAGE)"

# ── Deploy ─────────────────────────────────────────────────────────

.PHONY: apply
apply: apply-base apply-litellm apply-agent ## apply all manifests (fail-fast on missing secret)

.PHONY: apply-base
apply-base:
	kubectl --context $(KUBE_CONTEXT) apply -f $(MANIFESTS_DIR)/00-namespace.yaml

.PHONY: apply-litellm
apply-litellm:
	@test -f $(LITELLM_SECRET) || (echo "ERROR: $(LITELLM_SECRET) not found. Copy secret.yaml.example to secret.yaml and fill in AWS creds." && exit 1)
	kubectl --context $(KUBE_CONTEXT) apply -f $(MANIFESTS_DIR)/10-litellm/

.PHONY: apply-agent
apply-agent: build-agent
	kubectl --context $(KUBE_CONTEXT) apply -f $(MANIFESTS_DIR)/20-agent-service/

.PHONY: delete
delete: ## delete all deployed resources (keeps cluster + registry)
	kubectl --context $(KUBE_CONTEXT) delete -f $(MANIFESTS_DIR)/20-agent-service/ --ignore-not-found
	kubectl --context $(KUBE_CONTEXT) delete -f $(MANIFESTS_DIR)/10-litellm/ --ignore-not-found
	kubectl --context $(KUBE_CONTEXT) delete -f $(MANIFESTS_DIR)/00-namespace.yaml --ignore-not-found

# ── Day-to-day ─────────────────────────────────────────────────────

.PHONY: chat
chat: ## port-forward agent-service and POST a sample message
	kubectl --context $(KUBE_CONTEXT) port-forward -n $(NAMESPACE) svc/agent-service $(PORT_AGENT):8080 >/dev/null 2>&1 &
	PF_PID=$$!; \
	trap "kill $$PF_PID >/dev/null 2>&1 || true" EXIT; \
	sleep 2; \
	curl -sN -X POST http://localhost:$(PORT_AGENT)/chat \
		-H 'Content-Type: application/json' \
		-d '{"message":"list my clusters"}'

.PHONY: logs-agent
logs-agent: ## tail agent-service logs
	kubectl --context $(KUBE_CONTEXT) logs -n $(NAMESPACE) -l app=agent-service -f --tail=100

.PHONY: logs-litellm
logs-litellm: ## tail litellm logs
	kubectl --context $(KUBE_CONTEXT) logs -n $(NAMESPACE) -l app=litellm -f --tail=100

.PHONY: test
test: ## run pytest inside the agent-service image
	docker run --rm -v $(PWD)/$(AGENT_DIR):/app -w /app python:3.12-slim bash -c "pip install uv==0.5.4 && uv sync && uv run pytest"

.PHONY: shell-agent
shell-agent: ## exec into the running agent-service pod
	kubectl --context $(KUBE_CONTEXT) exec -n $(NAMESPACE) -it $$(kubectl --context $(KUBE_CONTEXT) get pod -n $(NAMESPACE) -l app=agent-service -o jsonpath='{.items[0].metadata.name}') -- /bin/sh
