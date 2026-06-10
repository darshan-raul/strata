"""Mocked tool: get the status of one EKS cluster by id."""
from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel


class ClusterStatus(BaseModel):
    id: str
    name: str
    status: str
    region: str
    k8s_version: str
    last_updated: str
    node_groups: int


@tool("get_cluster_status")
def get_cluster_status(cluster_id: str) -> dict:
    """Get the current status of one EKS cluster by its id (e.g. 'cl-001').

    Returns the cluster's status, region, Kubernetes version, when it
    was last updated, and how many node groups it has. Use this when
    the user asks for the status of a specific cluster, or after a
    provision/delete to confirm it finished.
    """
    if cluster_id == "cl-001":
        return ClusterStatus(
            id="cl-001",
            name="demo",
            status="READY",
            region="us-west-2",
            k8s_version="1.29",
            last_updated="2026-06-09T12:00:00Z",
            node_groups=2,
        ).model_dump()
    if cluster_id == "cl-002":
        return ClusterStatus(
            id="cl-002",
            name="staging",
            status="PROVISIONING",
            region="us-east-1",
            k8s_version="1.30",
            last_updated="2026-06-10T08:00:00Z",
            node_groups=0,
        ).model_dump()
    return ClusterStatus(
        id=cluster_id,
        name="unknown",
        status="NOT_FOUND",
        region="-",
        k8s_version="-",
        last_updated="-",
        node_groups=0,
    ).model_dump()
