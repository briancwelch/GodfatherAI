"""Real durable action approval, worker execution, authorization, fencing and no replay."""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from godfather_api import workflow_service
from godfather_api.models import Job, Node, WorkspaceMember
from godfather_api.provision import provision
from godfather_contracts import Registration
from godfather_contracts.jobs import Assignment
from godfather_contracts.result_actions import ACTION_RUNTIME, PATCH_RUNTIME, TARGET_PREFIX
from godfather_worker.result_actions import execute_action

from tests.integration.test_inference import APIWorkerClient
from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import create, enable, run_worker, submit
from tests.test_result_actions import setup

pytestmark = pytest.mark.integration


def prepared(h: Harness, tmp_path: Path) -> tuple[Any, dict[str, Any], dict[str, str]]:
    config, output = setup(tmp_path)
    config.allowed_user_ids = [UUID(h.admin["owner_id"])]
    config.allowed_workspace_ids = [h.workspace_id]
    enable(h)
    source = submit(h, create(h))
    h.tick()
    assignment = h.poll()
    assert assignment
    run_worker(h, assignment)
    with h.database.sessions.begin() as session:
        job = session.get(Job, UUID(source["id"]))
        assert job is not None
        from godfather_api.jobs import current_attempt

        attempt = current_attempt(session, job)
        assert attempt is not None
        artifact = workflow_service.save_artifact(
            session,
            cast(FastAPI, h.client.app).state.artifacts,
            job,
            attempt,
            "step_output",
            output.model_dump(mode="json"),
        )
        reference = workflow_service.reference(artifact)
        job.result_refs = {**job.result_refs, "final_output": reference.model_dump(mode="json")}
    registration = Registration.model_validate(
        {
            **h.registrations[0].model_dump(),
            "runtimes": [
                *h.registrations[0].runtimes,
                ACTION_RUNTIME,
                PATCH_RUNTIME,
                TARGET_PREFIX + str(config.id),
            ],
            "tool_permissions": ["coding.workspace"],
            "coding_repositories": [
                {
                    "id": str(config.id),
                    "name": config.name,
                    "allowed_user_ids": config.allowed_user_ids,
                    "allowed_workspace_ids": config.allowed_workspace_ids,
                }
            ],
        }
    )
    response = h.client.post(
        "/api/v1/workers/register",
        headers=headers(h.workers[0]),
        json=registration.model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    h.registrations[0] = registration
    return config, source, {"artifact_id": str(reference.id), "checksum": reference.checksum}


def test_approved_result_runs_on_exact_worker_and_updates_parent(
    h: Harness, tmp_path: Path
) -> None:
    config, source, body = prepared(h, tmp_path)
    path = f"/api/v1/jobs/{source['id']}/result-actions"
    response = h.client.post(path, json=body, headers=headers(h.admin))
    assert response.status_code == 201, response.text
    assert (
        h.client.post(path, json=body, headers=headers(h.admin)).json()["job_id"]
        == response.json()["job_id"]
    )
    assert "return a - b" in (config.path / "calc.py").read_text()
    h.tick()
    assert h.poll(1) is None
    assignment = h.poll()
    assert assignment is not None
    asyncio.run(
        execute_action(
            APIWorkerClient(h, 0),
            UUID(h.workers[0]["credential_id"]),
            h.registrations[0],
            Assignment.model_validate(assignment),
            threading.Event(),
            [config],
        )
    )
    result = h.get(response.json()["job_id"])
    assert result["status"] == "COMPLETED" and result["result"]["state"] == "applied"
    assert "return a + b" in (config.path / "calc.py").read_text()
    parent = h.client.get(f"/api/v1/command-center/jobs/{source['id']}", headers=headers(h.admin))
    assert parent.status_code == 200, parent.text
    assert parent.json()["result_action"]["result"]["state"] == "applied"
    assert parent.json()["context"]["agent_name"]


def test_actions_reject_unreviewed_cross_owner_and_unsupported_workers(
    h: Harness, tmp_path: Path
) -> None:
    config, source, body = prepared(h, tmp_path)
    path = f"/api/v1/jobs/{source['id']}/result-actions"
    outsider = provision(h.database, "admin", email="not-project-owner@example.invalid")
    assert h.client.post(path, json=body).status_code == 401
    assert h.client.post(path, json=body, headers=headers(outsider)).status_code == 404
    assert (
        h.client.post(
            path, json={**body, "checksum": "0" * 64}, headers=headers(h.admin)
        ).status_code
        == 409
    )
    from godfather_api.models import Node

    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node is not None
        node.runtimes = {**node.runtimes, "runtimes": []}
    assert h.client.post(path, json=body, headers=headers(h.admin)).status_code == 409


def test_action_begin_once_fenced_and_never_retried(h: Harness, tmp_path: Path) -> None:
    _, source, body = prepared(h, tmp_path)
    response = h.client.post(
        f"/api/v1/jobs/{source['id']}/result-actions", json=body, headers=headers(h.admin)
    )
    assert response.status_code == 201, response.text
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    identity = {
        "session_id": str(h.registrations[0].session_id),
        "attempt_id": assignment["attempt_id"],
        "fencing_token": assignment["fencing_token"],
    }
    route = (
        f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/"
        f"{response.json()['job_id']}/result-action/begin"
    )
    assert (
        h.client.post(
            route, json={**identity, "fencing_token": 9999}, headers=headers(h.workers[0])
        ).status_code
        == 409
    )
    assert h.client.post(route, json=identity, headers=headers(h.workers[0])).status_code == 200
    assert h.client.post(route, json=identity, headers=headers(h.workers[0])).status_code == 409
    h.tick(datetime.now(UTC) + timedelta(seconds=180))
    assert h.get(response.json()["job_id"])["status"] == "FAILED"
    assert (
        h.client.post(
            f"/api/v1/jobs/{response.json()['job_id']}/retry", json={}, headers=headers(h.admin)
        ).status_code
        == 409
    )
    assert h.client.post(route, json=identity, headers=headers(h.workers[0])).status_code == 409


def test_conflicts_are_reported_and_explicit_reapproval_can_succeed(
    h: Harness, tmp_path: Path
) -> None:
    config, source, body = prepared(h, tmp_path)
    target = config.path / "calc.py"
    original = target.read_bytes()
    target.write_text("my local edits\n")
    route = f"/api/v1/jobs/{source['id']}/result-actions"
    first = h.client.post(route, json=body, headers=headers(h.admin)).json()
    h.tick()
    assignment = h.poll()
    assert assignment
    asyncio.run(
        execute_action(
            APIWorkerClient(h, 0),
            UUID(h.workers[0]["credential_id"]),
            h.registrations[0],
            Assignment.model_validate(assignment),
            threading.Event(),
            [config],
        )
    )
    assert h.get(first["job_id"])["result"]["state"] == "blocked"
    assert target.read_text() == "my local edits\n"
    target.write_bytes(original)
    second = h.client.post(route, json=body, headers=headers(h.admin)).json()
    assert second["job_id"] != first["job_id"]


def test_workspace_admin_cannot_apply_to_another_owners_computer(
    h: Harness, tmp_path: Path
) -> None:
    _, source, body = prepared(h, tmp_path)
    outsider = provision(h.database, "admin", email="workspace-admin-apply@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=h.workspace_id, user_id=UUID(outsider["owner_id"]), role="admin"
            )
        )
    response = h.client.post(
        f"/api/v1/jobs/{source['id']}/result-actions", json=body, headers=headers(outsider)
    )
    assert response.status_code == 403


@pytest.mark.parametrize("mode", ["permission", "cancel"])
def test_worker_permission_withdrawal_and_cancellation_block_begin(
    h: Harness, tmp_path: Path, mode: str
) -> None:
    _, source, body = prepared(h, tmp_path)
    action = h.client.post(
        f"/api/v1/jobs/{source['id']}/result-actions", json=body, headers=headers(h.admin)
    ).json()
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    identity = {
        "session_id": str(h.registrations[0].session_id),
        "attempt_id": assignment["attempt_id"],
        "fencing_token": assignment["fencing_token"],
    }
    route = (
        f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/"
        f"{action['job_id']}/result-action/begin"
    )
    if mode == "permission":
        with h.database.sessions.begin() as session:
            node = session.get(Node, UUID(h.workers[0]["credential_id"]))
            assert node
            node.runtimes = {**node.runtimes, "runtimes": []}
    else:
        assert (
            h.client.post(
                f"/api/v1/jobs/{action['job_id']}/cancel", json={}, headers=headers(h.admin)
            ).status_code
            == 200
        )
    assert h.client.post(route, json=identity, headers=headers(h.workers[0])).status_code == 409
