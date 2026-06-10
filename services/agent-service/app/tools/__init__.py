"""Mocked EKS tools, all returning Pydantic-shaped dicts.

Phase 2: every tool returns hardcoded data. Phase 3+ will swap these
for HTTP calls into the Go orchestrator. The function signatures and
return shapes are the contract — keep them stable.
"""
from app.tools.delete_cluster import delete_cluster
from app.tools.get_cluster_logs import get_cluster_logs
from app.tools.get_cluster_status import get_cluster_status
from app.tools.list_clusters import list_clusters
from app.tools.provision_cluster import provision_cluster

__all__ = [
    "delete_cluster",
    "get_cluster_logs",
    "get_cluster_status",
    "list_clusters",
    "provision_cluster",
]
