"""Mocked tool: list all EKS clusters in the user's account.

Phase 2 returns hardcoded data. The shape is the contract the
orchestrator will fill in for real in Phase 3+ — keep this in sync
with `services/orchestrator`'s GET /clusters response.
"""
from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel


class Cluster(BaseModel):
    id: str
    name: str
    status: str
    region: str
    k8s_version: str


_MOCK_CLUSTERS: list[Cluster] = [
    Cluster(id="cl-001", name="demo", status="READY", region="us-west-2", k8s_version="1.29"),
    Cluster(id="cl-002", name="staging", status="PROVISIONING", region="us-east-1", k8s_version="1.30"),
    Cluster(id="cl-003", name="scratch", status="FAILED", region="us-west-2", k8s_version="1.28"),
]


@tool("list_clusters")
def list_clusters() -> list[dict]:
    """List all EKS clusters in the user's account.

    Returns a list of cluster objects with id, name, status, region, and
    Kubernetes version. Use this when the user asks what clusters they
    have, what's running, or to enumerate by name.
    """
    return [c.model_dump() for c in _MOCK_CLUSTERS]
