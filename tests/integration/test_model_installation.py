"""Durable owner-only model installation, using the explicitly disposable database."""

from uuid import UUID

import pytest
from godfather_api.models import WorkspaceMember
from godfather_api.provision import provision
from godfather_contracts.model_management import (
    INSTALL_RUNTIME,
    PROVIDER_RUNTIME_PREFIX,
    SETUP_RUNTIME,
)

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import enable

pytestmark = pytest.mark.integration


def opt_in(h: Harness) -> None:
    enable(h)
    registration = h.registrations[0].model_copy(
        update={
            "runtimes": [
                *h.registrations[0].runtimes,
                INSTALL_RUNTIME,
                PROVIDER_RUNTIME_PREFIX + "local",
            ],
        }
    )
    response = h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[0]),
    )
    assert response.status_code == 200, response.text
    h.registrations[0] = registration


def payload(h: Harness) -> dict[str, object]:
    return {
        "workspace_id": str(h.workspace_id),
        "node_id": h.workers[0]["credential_id"],
        "provider_id": "local",
        "identifier": "qwen3:0.6b",
        "confirm_download": True,
    }


def test_runtime_setup_requires_separate_local_opt_in_and_is_durably_bound(h: Harness) -> None:
    opt_in(h)
    body = {**payload(h), "provider_id": "local-ollama", "install_runtime": True}
    assert (
        h.client.post("/api/v1/models/install", json=body, headers=headers(h.admin)).status_code
        == 409
    )
    registration = h.registrations[0].model_copy(
        update={
            "runtimes": [
                *h.registrations[0].runtimes,
                PROVIDER_RUNTIME_PREFIX + "local-ollama",
                SETUP_RUNTIME,
            ]
        }
    )
    assert (
        h.client.post(
            "/api/v1/workers/register",
            json=registration.model_dump(mode="json"),
            headers=headers(h.workers[0]),
        ).status_code
        == 200
    )
    response = h.client.post("/api/v1/models/install", json=body, headers=headers(h.admin))
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["input"]["install_runtime"] is True
    assert SETUP_RUNTIME in job["requirements"]["runtimes"]
    h.tick()
    assert h.poll(1) is None
    assignment = h.poll()
    assert assignment is not None and assignment["job"]["id"] == job["id"]


def test_install_requires_owner_opt_in_confirmation_and_catalog(h: Harness) -> None:
    body = payload(h)
    assert (
        h.client.post("/api/v1/models/install", json=body, headers=headers(h.admin)).status_code
        == 409
    )
    opt_in(h)
    assert (
        h.client.post(
            "/api/v1/models/install",
            json={**body, "confirm_download": False},
            headers=headers(h.admin),
        ).status_code
        == 422
    )
    assert (
        h.client.post(
            "/api/v1/models/install",
            json={**body, "identifier": "unapproved:latest"},
            headers=headers(h.admin),
        ).status_code
        == 422
    )
    outsider = provision(h.database, "admin", email="model-owner-outsider@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=h.workspace_id, user_id=UUID(outsider["owner_id"]), role="admin"
            )
        )
    assert (
        h.client.post("/api/v1/models/install", json=body, headers=headers(outsider)).status_code
        == 404
    )
    options = h.client.get(
        f"/api/v1/models/install-options?workspace_id={h.workspace_id}", headers=headers(outsider)
    ).json()
    assert options["nodes"] == []
    assert (
        h.client.get(
            f"/api/v1/models/install-options?workspace_id={h.workspace_id}",
            headers=headers(h.workers[0]),
        ).status_code
        == 401
    )


def test_install_is_durable_pinned_and_uses_existing_fenced_reports(h: Harness) -> None:
    opt_in(h)
    response = h.client.post("/api/v1/models/install", json=payload(h), headers=headers(h.admin))
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["type"] == "model.install" and job["retry"]["limit"] == 0
    assert (
        h.client.post(
            "/api/v1/models/install", json=payload(h), headers=headers(h.admin)
        ).status_code
        == 409
    )
    assert h.tick() == 1
    assert h.poll(1) is None
    assignment = h.poll()
    assert assignment is not None and assignment["job"]["id"] == job["id"]
    h.start(assignment)
    h.report(assignment, "progress", progress=45)
    h.report(
        assignment,
        "complete",
        result={"identifier": "qwen3:0.6b", "provider_id": "local", "installed": True},
    )
    assert h.get(job["id"])["result"]["installed"] is True
    h.report(
        assignment,
        "complete",
        expected=409,
        result={"identifier": "qwen3:0.6b", "provider_id": "local", "installed": True},
    )


def test_cancelled_or_withdrawn_install_cannot_report_completion(h: Harness) -> None:
    opt_in(h)
    response = h.client.post("/api/v1/models/install", json=payload(h), headers=headers(h.admin))
    job = response.json()
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)).status_code
        == 200
    )
    h.report(
        assignment,
        "complete",
        result={"identifier": "qwen3:0.6b", "provider_id": "local", "installed": True},
    )
    assert h.get(job["id"])["status"] == "CANCELLED"
