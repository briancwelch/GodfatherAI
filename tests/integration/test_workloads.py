"""Real PostgreSQL workload durability, fencing, downloads and workspace boundaries."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from godfather_api.provision import provision
from godfather_worker import data_program

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import expire, get, step
from tests.test_workloads import source

pytestmark = pytest.mark.integration


def enable_data(h: Harness, index: int) -> None:
    registration = h.registrations[index].model_copy(
        update={
            "workflow_protocol_version": 1,
            "primary_capabilities": ["analytics", "reporting"] if index == 0 else ["cpu"],
            "secondary_capabilities": [] if index == 0 else ["analytics", "reporting"],
            "runtimes": ["data-workloads-v1"],
            "tool_permissions": ["data.analyze"],
        }
    )
    response = h.client.post(
        "/api/v1/workers/register",
        headers=headers(h.workers[index]),
        json=registration.model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    h.registrations[index] = registration


def submit_data(h: Harness, **values: Any) -> dict[str, Any]:
    response = h.client.post(
        "/api/v1/workloads/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "kind": "report",
            "input": {
                "instruction": "Isolated deterministic fixture only",
                "dataset": source(),
                "report_format": "html",
            },
            **values,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_data_failover_preserves_analysis_fences_stale_node_and_downloads(h: Harness) -> None:
    enable_data(h, 0)
    enable_data(h, 1)
    job = submit_data(h)
    assert h.tick() == 1
    first = h.poll()
    assert first is not None and "deployment" not in first
    h.start(first)
    analysis = data_program.analyze({"dataset": source()})
    step(h, first, "analytics", 0)
    state = step(h, first, "analytics", 0, "checkpoint", output=analysis)
    assert state["checkpoint_version"] == 1
    expire(h, first)
    with h.database.sessions.begin() as session:
        from godfather_api.models import Job

        row = session.get(Job, UUID(job["id"]))
        assert row is not None
        row.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
    assert h.tick() == 1
    second = h.poll(1)
    assert second is not None and second["workflow"]["state"]["current_step"] == 1
    assert second["fencing_token"] > first["fencing_token"]
    step(h, first, "report", 1, expected=409)
    h.start(second, 1)
    step(h, second, "report", 1, index=1)
    report = data_program.report({"context": analysis, "report_format": "html"})
    state = step(h, second, "report", 1, "checkpoint", index=1, output=report)
    h.report(
        second,
        "complete",
        1,
        result={
            "workflow_id": second["workflow"]["state"]["workflow_id"],
            "workflow_version": 1,
            "agent_id": second["workflow"]["agent"]["id"],
            "agent_version": 1,
            "checkpoint_version": 2,
            "completed_steps": ["analytics", "report"],
            "final_output": state["completed"][-1]["output"],
        },
    )
    ref = state["completed"][-1]["output"]["id"]
    path = f"/api/v1/workloads/jobs/{job['id']}/files/{ref}/0"
    download = h.client.get(path, headers=headers(h.admin))
    assert download.status_code == 200 and b"Analysis report" in download.content
    assert download.headers["content-disposition"].startswith("attachment")
    assert h.client.get(path).status_code == 401
    outsider = provision(h.database, "admin", email="different-dataset-owner@example.invalid")
    assert h.client.get(path, headers=headers(outsider)).status_code == 404
    assert get(h, job["id"], "/result")["output"]["analysis"] == analysis["analysis"]
    # An application restart reloads immutable files and checkpoint references from PostgreSQL.
    from fastapi.testclient import TestClient
    from godfather_api.app import create_app
    from godfather_api.config import Settings

    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        assert restarted.get(path, headers=headers(h.admin)).content == download.content
    # New tasks reuse the immutable built-in agent instead of creating unrelated definitions.
    assert submit_data(h)["requirements"] == job["requirements"]


def test_availability_input_validation_and_withdrawn_owner_permission(h: Harness) -> None:
    options = h.client.get(
        f"/api/v1/workloads/options?workspace_id={h.workspace_id}", headers=headers(h.admin)
    ).json()
    assert all(not n["analytics"] and not n["image_models"] for n in options["nodes"])
    assert options["cloud_images"] is False and options["sql_sources"] == []
    enable_data(h, 0)
    job = submit_data(h)
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    from godfather_api.models import Node

    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node is not None
        node.runtimes = {**node.runtimes, "tool_permissions": []}
    step(h, assignment, "analytics", 0, expected=403)
    assert h.get(job["id"])["checkpoint_ref"] is None
    response = h.client.post(
        "/api/v1/workloads/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "kind": "analytics",
            "input": {"instruction": "no dataset"},
        },
    )
    assert response.status_code == 422
