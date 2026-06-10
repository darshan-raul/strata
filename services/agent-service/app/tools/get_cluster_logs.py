"""Mocked tool: get the last N log lines for a cluster."""
from __future__ import annotations

from langchain_core.tools import tool

_MOCK_LOGS: dict[str, list[str]] = {
    "cl-001": [
        "2026-06-09T12:00:00Z INFO  cluster demo is READY",
        "2026-06-09T12:00:01Z INFO  argocd application ops-repo synced",
        "2026-06-09T12:00:02Z INFO  all node groups healthy",
    ],
    "cl-002": [
        "2026-06-10T08:00:00Z INFO  provision started",
        "2026-06-10T08:01:00Z INFO  vpc created",
        "2026-06-10T08:02:00Z INFO  eks cluster creating",
    ],
    "cl-003": [
        "2026-06-08T20:00:00Z ERROR terraform apply failed: insufficient capacity",
        "2026-06-08T20:00:01Z ERROR status set to FAILED",
    ],
}


@tool("get_cluster_logs")
def get_cluster_logs(cluster_id: str, lines: int = 20) -> list[str]:
    """Return the last `lines` log lines for one EKS cluster.

    Use this to investigate failures or to answer 'what happened with
    cluster X'. Returns at most `lines` lines, newest first.
    """
    logs = _MOCK_LOGS.get(cluster_id, [f"no logs found for cluster {cluster_id}"])
    return logs[-lines:]
