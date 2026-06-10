"""Tests for the mocked tools.

These run without any LLM or external services. They check that the
tools return well-shaped data and that the tool descriptions survive
intact (the LLM sees the description, so it matters).
"""
from __future__ import annotations

from app.tools import (
    delete_cluster,
    get_cluster_logs,
    get_cluster_status,
    list_clusters,
    provision_cluster,
)


def test_list_clusters_returns_three_mocked_rows() -> None:
    out = list_clusters.invoke({})
    assert isinstance(out, list)
    assert len(out) == 3
    for row in out:
        assert set(row.keys()) == {"id", "name", "status", "region", "k8s_version"}


def test_get_cluster_status_known_id() -> None:
    out = get_cluster_status.invoke({"cluster_id": "cl-001"})
    assert out["id"] == "cl-001"
    assert out["status"] == "READY"
    assert out["region"] == "us-west-2"


def test_get_cluster_status_unknown_id_returns_not_found() -> None:
    out = get_cluster_status.invoke({"cluster_id": "cl-does-not-exist"})
    assert out["status"] == "NOT_FOUND"


def test_get_cluster_logs_default_lines() -> None:
    out = get_cluster_logs.invoke({"cluster_id": "cl-001"})
    assert isinstance(out, list)
    assert len(out) >= 1
    assert "READY" in out[0]


def test_get_cluster_logs_respects_lines_param() -> None:
    out = get_cluster_logs.invoke({"cluster_id": "cl-001", "lines": 1})
    assert len(out) == 1


def test_get_cluster_logs_unknown_id_returns_message() -> None:
    out = get_cluster_logs.invoke({"cluster_id": "cl-missing"})
    assert isinstance(out, list)
    assert "no logs found" in out[0]


def test_provision_cluster_returns_initiated() -> None:
    out = provision_cluster.invoke(
        {"name": "new-cluster", "region": "us-west-2", "k8s_version": "1.29"}
    )
    assert out["status"] == "INITIATED"
    assert out["name"] == "new-cluster"
    assert out["id"].startswith("cl-")


def test_delete_cluster_returns_deleting() -> None:
    out = delete_cluster.invoke({"cluster_id": "cl-001"})
    assert out == {"id": "cl-001", "status": "DELETING"}


def test_tool_descriptions_are_present() -> None:
    """The LLM sees the tool description. Empty description = bad UX."""
    for fn in (list_clusters, get_cluster_status, get_cluster_logs, provision_cluster, delete_cluster):
        assert fn.description, f"{fn.name} has no description"
        assert len(fn.description) > 20, f"{fn.name} description is suspiciously short"
