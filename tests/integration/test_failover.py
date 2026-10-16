"""Deterministic Windows-to-macOS/Linux recovery and safety fault injection."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from godfather_api.artifacts import LocalArtifactStore
from godfather_api.models import AccessCredential, Attempt, Node, WorkflowRun, WorkspaceMember
from godfather_api.provision import provision
from godfather_contracts import Heartbeat

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import (
    create,
    enable,
    expire,
    first_checkpoint,
    get,
    run_worker,
    step,
    submit,
)
from tests.workflow_helpers import sample_definition

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("backup_os", ["macos", "linux"])
def test_cross_owner_coding_workflow_recovers_committed_prefix_and_fences_reconnection(
    h: Harness, backup_os: str
) -> None:
    enable(h)
    enable(h, 1)
    vegas = provision(h.database, "admin", email="vegas-owner@example.invalid")
    with h.database.sessions.begin() as session:
        credential = session.get(AccessCredential, UUID(h.workers[0]["credential_id"]))
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert credential is not None and node is not None
        credential.owner_id = node.owner_id = UUID(vegas["owner_id"])
        session.add(
            WorkspaceMember(workspace_id=h.workspace_id, user_id=node.owner_id, role="member")
        )
        node.contribution_policy = {
            "allowed_job_owner_ids": [h.admin["owner_id"]],
            "allowed_workspace_ids": [str(h.workspace_id)],
        }
        backup = session.get(Node, UUID(h.workers[1]["credential_id"]))
        assert backup is not None
        backup.os = backup_os
    spec = sample_definition()
    spec.requirements.capabilities = ["coding"]
    job = submit(h, create(h, spec))
    assert h.tick() == 1
    original = h.poll()
    assert original is not None and h.poll(1) is None
    checkpoint = first_checkpoint(h, original)
    expire(h, original)
    recovered = h.poll(1)
    assert recovered is not None
    assert recovered["workflow"]["state"]["context"] == checkpoint["context"]
    assert recovered["workflow"]["state"]["current_step"] == 1
    assert recovered["fencing_token"] > original["fencing_token"]
    provider = run_worker(h, recovered, index=1)
    assert len(provider.calls) == 1
    final = get(h, job["id"], "/result")
    assert final["status"] == "COMPLETED"
    # Original authenticated process reconnects after recovery: its old attempt stays fenced.
    response = h.client.post(
        f"/api/v1/workers/{h.workers[0]['credential_id']}/heartbeat",
        headers=headers(h.workers[0]),
        json=Heartbeat(
            session_id=h.registrations[0].session_id, resources=h.registrations[0].resources
        ).model_dump(mode="json"),
    )
    assert response.status_code == 200
    step(h, original, "describe", 1, expected=409)
    h.report(original, "renew", expected=409)
    assert get(h, job["id"], "/result") == final
    details = h.client.get(
        f"/api/v1/command-center/jobs/{job['id']}", headers=headers(h.admin)
    ).json()
    assert [a["status"] for a in details["attempts"]] == ["INTERRUPTED", "COMPLETED"]
    assert details["attempts"][1]["recovered_from_attempt_id"] == original["attempt_id"]
    assert details["attempts"][1]["resumed_checkpoint_version"] == 1
    assert len(details["checkpoints"]) == 3
    assert len(details["steps"]) == 3
    recovery = [e for e in details["events"]["items"] if e["type"] == "job.recovery.assigned"]
    assert len(recovery) == 1 and recovery[0]["details"]["cross_node"] is True


@pytest.mark.parametrize(
    "constraint",
    [
        "os",
        "architecture",
        "model",
        "tools",
        "resources",
        "workspace",
        "protocol",
        "runtime",
        "disabled_agent",
    ],
)
def test_incompatible_backup_stays_queued_without_losing_checkpoint(
    h: Harness, constraint: str
) -> None:
    enable(h)
    enable(h, 1)
    spec = sample_definition()
    if constraint == "os":
        spec.requirements.os = "windows"
    elif constraint == "architecture":
        spec.requirements.architecture = "x86_64"
    elif constraint == "runtime":
        spec.requirements.runtimes = ["windows-sdk"]
        with h.database.sessions.begin() as session:
            node = session.get(Node, UUID(h.workers[0]["credential_id"]))
            assert node is not None
            node.runtimes = {**node.runtimes, "runtimes": ["windows-sdk"]}
    agent = create(h, spec)
    job = submit(h, agent)
    h.tick()
    a = h.poll()
    assert a is not None
    first_checkpoint(h, a)
    with h.database.sessions.begin() as session:
        backup = session.get(Node, UUID(h.workers[1]["credential_id"]))
        assert backup is not None
        if constraint == "model":
            backup.runtimes = {**backup.runtimes, "model_deployments": []}
        elif constraint == "tools":
            backup.runtimes = {**backup.runtimes, "tool_permissions": []}
        elif constraint == "resources":
            backup.resources = {**backup.resources, "cpu_count": 1}
            # First node has 8 CPUs. Require two for recovery.
            from godfather_api.models import Job

            row = session.get(Job, UUID(job["id"]))
            assert row is not None
            row.requirements = {**row.requirements, "cpu_count": 2}
        elif constraint == "workspace":
            outsider = provision(h.database, "admin", email="no-grant@example.invalid")
            backup.owner_id = UUID(outsider["owner_id"])
        elif constraint == "protocol":
            backup.runtimes = {**backup.runtimes, "workflow_protocol_version": None}
    if constraint == "disabled_agent":
        assert (
            h.client.post(
                f"/api/v1/agents/{agent['id']}/versions/1/control",
                headers=headers(h.admin),
                json={"action": "disable"},
            ).status_code
            == 200
        )
    expire(h, a)
    assert h.get(job["id"])["status"] == "PENDING"
    assert h.poll(1) is None
    assert len(get(h, job["id"], "/checkpoints")) == 1


def test_corrupt_committed_output_pauses_for_review_without_retry_loop(h: Harness) -> None:
    enable(h)
    enable(h, 1)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    checkpoint = first_checkpoint(h, a)
    store: LocalArtifactStore = cast(FastAPI, h.client.app).state.artifacts
    store.path(UUID(checkpoint["completed"][0]["output"]["id"])).write_bytes(b"broken")
    expire(h, a)
    for _ in range(3):
        assert h.tick() == 0
    response = h.client.get(f"/api/v1/command-center/jobs/{job['id']}", headers=headers(h.admin))
    assert response.status_code == 200
    assert response.json()["workflow"]["status"] == "REVIEW_REQUIRED"
    assert response.json()["job"]["attempt_count"] == 1


def test_mismatched_pinned_workflow_version_requires_review(h: Harness) -> None:
    enable(h)
    enable(h, 1)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    first_checkpoint(h, a)
    with h.database.sessions.begin() as session:
        run = session.get(WorkflowRun, UUID(job["id"]))
        assert run is not None
        run.workflow_version += 1
    expire(h, a)
    assert h.poll(1) is None
    detail = h.client.get(
        f"/api/v1/command-center/jobs/{job['id']}", headers=headers(h.admin)
    ).json()
    assert detail["workflow"]["status"] == "REVIEW_REQUIRED"
    assert detail["job"]["attempt_count"] == 1


def test_partitioned_process_cancellation_and_bounded_recovery(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    first_checkpoint(h, a)
    # Lease expires while heartbeat stays healthy: no same-session restart.
    with h.database.sessions.begin() as session:
        attempt = session.get(Attempt, UUID(a["attempt_id"]))
        assert attempt is not None
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    h.tick()
    h.tick()
    assert h.poll() is None and h.get(job["id"])["status"] == "PENDING"
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)).status_code
        == 200
    )
    enable(h, 1)
    assert h.tick() == 0 and h.get(job["id"])["status"] == "CANCELLED"


def test_repeated_failures_exhaust_automatic_budget_and_manual_retry_is_bounded(h: Harness) -> None:
    enable(h)
    enable(h, 1)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    first_checkpoint(h, a)
    expire(h, a)
    b = h.poll(1)
    assert b is not None
    h.start(b, 1)
    h.report(b, "fail", 1, error_code="provider_unavailable")
    assert h.get(job["id"])["status"] == "FAILED"
    assert h.tick() == 0
    response = h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin))
    assert response.status_code == 200 and response.json()["attempt_count"] == 2
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin)).status_code
        == 409
    )
