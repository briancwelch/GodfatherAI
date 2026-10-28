"""Node-scoped job metadata and durable lifecycle events against disposable PostgreSQL."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from godfather_api.models import Attempt, Event, WorkspaceMember
from sqlalchemy import select

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h

pytestmark = pytest.mark.integration
ROUTE = "/api/v1/workers/activity/jobs"


def read(h: Harness, index: int = 0, **payload: Any) -> dict[str, Any]:
    response = h.client.post(ROUTE, json=payload, headers=headers(h.workers[index]))
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_history_and_fast_job_lifecycle_are_node_scoped_and_secret_free(h: Harness) -> None:
    assert h.client.post(ROUTE, json={}).status_code == 401
    assert h.client.post(ROUTE, json={}, headers=headers(h.admin)).status_code == 401
    baseline = read(h)
    assert baseline["jobs"] == baseline["events"] == []
    job = h.submit(input={"value": "private-prompt-never-in-activity"})
    h.tick()
    assignment = h.poll()
    assert assignment
    h.complete(assignment)
    result = read(h, cursor=baseline["cursor"])
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["job_id"] == job["id"]
    assert result["jobs"][0]["status"] == "COMPLETED"
    assert {event["type"] for event in result["events"]} == {
        "job.assigned",
        "job.started",
        "job.completed",
    }
    assert "private-prompt-never-in-activity" not in str(result)
    assert "fencing_token" not in str(result) and "result" not in result["jobs"][0]
    assert read(h, 1)["jobs"] == []
    assert read(h, cursor=result["cursor"])["events"] == []
    assert (
        h.client.post(
            ROUTE, json={"node_id": h.workers[1]["credential_id"]}, headers=headers(h.workers[0])
        ).status_code
        == 422
    )
    assert read(h)["events"] == []  # First connection does not announce history.
    with h.database.sessions.begin() as session:
        attempt = session.scalar(select(Attempt).where(Attempt.job_id == UUID(job["id"])))
        assert attempt
        attempt.result = {"shared_sessions": {h.workers[1]["credential_id"]: "fixture-session"}}
    peer = read(h, 1)
    assert peer["jobs"][0]["shared"] and peer["jobs"][0]["job_id"] == job["id"]


def test_history_pagination_and_removed_workspace_access(h: Harness) -> None:
    for _ in range(3):
        h.submit()
        h.tick()
        assignment = h.poll()
        assert assignment
        h.complete(assignment)
    first, second = read(h, limit=2), read(h, limit=2, offset=2)
    assert len(first["jobs"]) == 2 and first["has_more"]
    assert len(second["jobs"]) == 1 and not second["has_more"]
    assert not {j["attempt_id"] for j in first["jobs"]} & {j["attempt_id"] for j in second["jobs"]}
    assert len(read(h, job_id=first["jobs"][0]["job_id"])["jobs"]) == 1
    # A different owner's worker has no membership in the existing workspace.
    from godfather_api.models import AccessCredential, User

    with h.database.sessions.begin() as session:
        owner = User(
            email="activity-private@example.invalid", display_name="Private", role="member"
        )
        session.add(owner)
        session.flush()
        credential = session.get(AccessCredential, UUID(h.workers[0]["credential_id"]))
        assert credential and credential.node_id
        from godfather_api.models import Node

        node = session.get(Node, credential.node_id)
        assert node
        credential.owner_id = node.owner_id = owner.id
        assert session.get(WorkspaceMember, (h.workspace_id, owner.id)) is None
    assert read(h)["jobs"] == []


def test_event_cursor_pages_same_timestamp_events_without_losing_transitions(h: Harness) -> None:
    baseline = read(h)
    job = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    result = read(h, cursor=baseline["cursor"])
    now = datetime.now(UTC) + timedelta(seconds=1)
    with h.database.sessions.begin() as session:
        for _ in range(105):
            session.add(
                Event(
                    job_id=UUID(job["id"]),
                    workspace_id=h.workspace_id,
                    attempt_id=UUID(assignment["attempt_id"]),
                    node_id=UUID(h.workers[0]["credential_id"]),
                    type="job.started",
                    created_at=now,
                )
            )
    first = read(h, cursor=result["cursor"])
    second = read(h, cursor=first["cursor"])
    assert len(first["events"]) == 100 and first["more_events"]
    assert len(second["events"]) == 5 and not second["more_events"]
    assert not {e["id"] for e in first["events"]} & {e["id"] for e in second["events"]}


def test_cancelled_and_failed_attempts_produce_confirmed_notices(h: Harness) -> None:
    baseline = read(h)
    job = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin))
    h.report(assignment, "cancelled")
    h.submit()
    h.tick()
    failed = h.poll()
    assert failed
    h.start(failed)
    h.report(failed, "fail", error_code="permanent_error")
    result = read(h, cursor=baseline["cursor"])
    assert {e["type"] for e in result["events"]} >= {
        "job.started",
        "job.cancelled",
        "job.cancellation_requested",
        "job.attempt_failed",
    }
    assert {j["status"] for j in result["jobs"]} == {"CANCELLED", "FAILED"}
