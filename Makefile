SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Strata v2 — top-level dev workflow. See AGENTS.md for the full plan.

.DEFAULT_GOAL := help

.PHONY: help
help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── TUI ──────────────────────────────────────────────────────────

.PHONY: tui-dev
tui-dev: ## install + run the Strata TUI (uv)
	cd tui && uv sync && uv run strata

.PHONY: tui-test
tui-test: ## run TUI pytest suite
	cd tui && uv sync --all-extras && uv run --all-extras pytest

.PHONY: tui-lint
tui-lint: ## ruff lint the TUI
	cd tui && uv sync --all-extras && uv run --all-extras ruff check strata_tui tests

# ── Backend (Phase 1+) ──────────────────────────────────────────

.PHONY: backend-up
backend-up: ## bring up a local kind cluster + helm install the Strata chart
	@echo "backend-up: lands in Phase 1"

.PHONY: backend-down
backend-down: ## tear down the local backend
	@echo "backend-down: lands in Phase 1"

.PHONY: backend-logs
backend-logs: ## tail logs across all backend pods
	@echo "backend-logs: lands in Phase 1"

.PHONY: backend-rebuild
backend-rebuild: ## rebuild backend images + restart pods
	@echo "backend-rebuild: lands in Phase 1"

# ── Docs ─────────────────────────────────────────────────────────

.PHONY: docs-list
docs-list: ## list the docs library
	@ls docs/

# ── Reset ────────────────────────────────────────────────────────

.PHONY: reset
reset: ## nuke .venv, __pycache__, .pytest_cache, .ruff_cache, uv.lock (be careful)
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	@rm -rf tui/.venv tui/uv.lock 2>/dev/null || true
	@echo "reset complete"