"""Mocked tool: provision a new EKS cluster.

Phase 2 returns a fake INITIATED result. In Phase 3+ this becomes an
HTTP POST to the orchestrator, which kicks the real provision flow.
"""
from __future__ import annotations

import uuid

from langchain_core.tools import tool


@tool("provision_cluster")
def provision_cluster(name: str, region: str, k8s_version: str) -> dict:
    """Provision a new EKS cluster.

    Args:
        name: Human-readable cluster name (lowercase, no spaces).
        region: AWS region (e.g. 'us-west-2', 'us-east-1').
        k8s_version: Kubernetes version (e.g. '1.29', '1.30').

    Returns:
        A dict with the new cluster's id and status (INITIATED).
    """
    new_id = f"cl-{uuid.uuid4().hex[:6]}"
    return {
        "id": new_id,
        "name": name,
        "region": region,
        "k8s_version": k8s_version,
        "status": "INITIATED",
    }
