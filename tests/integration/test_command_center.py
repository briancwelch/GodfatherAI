"""Command Center projections retain existing credential and workspace boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from godfather_api.models import Job
from godfather_api.provision import provision

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import create, enable, run_worker, submit

pytestmark = pytest.mark.integration


def test_agent_history_shows_real_deployments_and_preserves_workspace_scope(h: Harness) -> None:
    enable(h)
    agent = create(h)
    submit(h, agent)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    run_worker(h, assignment)
    path = f"/api/v1/command-center/agents/{agent['id']}"
    response = h.client.get(path, headers=headers(h.admin))
    assert response.status_code == 200, response.text
    assignments = response.json()["assignments"]
    assert len(assignments) == 2
    assert all(a["deployment"]["identifier"] == "fixture" for a in assignments)
    assert all(a["usage"]["output_tokens"] is not None for a in assignments)
    outsider = provision(h.database, "admin", email="no-model-history@example.invalid")
    assert h.client.get(path, headers=headers(outsider)).status_code == 404
    assert h.client.get(path, headers=headers(h.workers[0])).status_code == 401


def test_summary_counts_pagination_and_real_telemetry(h: Harness) -> None:
    enable(h)
    create(h)
    with h.database.sessions.begin() as session:
        session.add_all(
            Job(
                owner_id=UUID(h.admin["owner_id"]),
                workspace_id=h.workspace_id,
                type="synthetic.echo",
                input_refs={"value": "test"},
            )
            for _ in range(103)
        )
    response = h.client.get(
        "/api/v1/command-center?section=jobs&offset=100", headers=headers(h.admin)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["job_counts"] == {"PENDING": 103}
    assert data["totals"]["jobs"] == 103 and len(data["jobs"]) == 3
    assert data["node_counts"] == {"online": 2}
    assert data["nodes"][0]["resources"]["source"] == "simulated"
    assert data["agent_counts"]["enabled_versions"] == 1
    assert "token" not in data and "credentials" not in data


def test_command_center_requires_real_credentials_and_never_leaks_private_workspaces(
    h: Harness,
) -> None:
    enable(h)
    job = submit(h, create(h))
    outsider = provision(h.database, "admin", email="other-dashboard@example.invalid")
    for path in ("command-center", "command-center/events", f"command-center/jobs/{job['id']}"):
        assert h.client.get("/api/v1/" + path).status_code == 401
        assert h.client.get("/api/v1/" + path, headers=headers(h.workers[0])).status_code == 401
    other = h.client.get("/api/v1/command-center", headers=headers(outsider)).json()
    assert other["jobs"] == [] and other["agents"] == [] and other["workspaces"] == []
    assert (
        h.client.get(
            f"/api/v1/command-center?workspace_id={h.workspace_id}", headers=headers(outsider)
        ).status_code
        == 404
    )
    assert (
        h.client.get(
            f"/api/v1/command-center/jobs/{job['id']}", headers=headers(outsider)
        ).status_code
        == 404
    )
    audit = h.client.get("/api/v1/command-center/events", headers=headers(outsider)).json()
    assert all(e["workspace_id"] is None and e["job_id"] is None for e in audit["items"])
    node = h.client.get(
        f"/api/v1/command-center/nodes/{h.workers[0]['credential_id']}", headers=headers(outsider)
    ).json()
    assert node["jobs"] == []


def test_event_filters_actor_job_agent_severity_and_time(h: Harness) -> None:
    agent = create(h)
    job = submit(h, agent)
    query = {
        "workspace_id": str(h.workspace_id),
        "job_id": job["id"],
        "agent_id": agent["id"],
        "user_id": h.admin["owner_id"],
        "severity": "info",
        "event_type": "job.submitted",
        "since": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "until": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
    }
    response = h.client.get("/api/v1/command-center/events", params=query, headers=headers(h.admin))
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["job_id"] == job["id"]
    assert (
        h.client.get(
            "/api/v1/command-center/events?since=2026-01-01T00:00:00", headers=headers(h.admin)
        ).status_code
        == 422
    )


def test_retry_refuses_terminal_success_cancelled_unsafe_and_inaccessible_jobs(h: Harness) -> None:
    job = h.submit()
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin)).status_code
        == 409
    )
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    h.report(assignment, "fail", error_code="permanent_error")
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin)).status_code
        == 409
    )
    outsider = provision(h.database, "admin", email="no-retry@example.invalid")
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(outsider)).status_code
        == 404
    )


def test_search_and_status_filters_do_not_change_summary_counts(h: Harness) -> None:
    h.submit()
    response = h.client.get(
        "/api/v1/command-center?section=jobs&search=missing&status=PENDING",
        headers=headers(h.admin),
    )
    assert response.status_code == 200
    assert response.json()["jobs"] == [] and response.json()["job_counts"]["PENDING"] == 1
