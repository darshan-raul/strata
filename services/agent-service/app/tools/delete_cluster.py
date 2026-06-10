"""Mocked tool: deprovision (delete) an EKS cluster.

Phase 2 returns a fake DELETING result. In Phase 3+ this becomes an
HTTP DELETE to the orchestrator, which runs the real deprovision flow.
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool("delete_cluster")
def delete_cluster(cluster_id: str) -> dict:
    """Deprovision an EKS cluster by its id.

    Args:
        cluster_id: The cluster id to delete (e.g. 'cl-001').

    Returns:
        A dict with the cluster's id and status (DELETING).
    """
    return {
        "id": cluster_id,
        "status": "DELETING",
    }
