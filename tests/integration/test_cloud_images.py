"""PostgreSQL authorization and worker image delivery; cloud HTTP is mocked."""

import asyncio
import threading
from typing import Any
from uuid import UUID

import pytest
from godfather_api.models import (
    AccountProviderKey,
    ProviderConnection,
    ProviderInvocation,
    Workspace,
    WorkspaceMember,
)
from godfather_api.provision import provision
from godfather_contracts import ModelDeployment
from godfather_contracts.jobs import Assignment
from godfather_contracts.providers import ConnectionPolicy
from godfather_model_gateway import GatewayError
from godfather_model_gateway.images import CloudImageResult, CloudImages
from godfather_worker.agents import execute_agent
from sqlalchemy import select

from tests.integration.test_inference import APIWorkerClient
from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import get, step
from tests.test_cloud_images import config, png

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_restricted_workspace_shows_image_inventory_and_explicit_allow_unlocks_submission(
    h: Harness,
    provider: str,
) -> None:
    connection, _ = enable(h, provider)
    model = config(provider).model_catalog[0].identifier
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace is not None
        workspace.allowed_models = []
    path = f"/api/v1/workloads/options?workspace_id={h.workspace_id}"
    options = h.client.get(path, headers=headers(h.admin)).json()
    assert options["cloud_image_models"] == []
    blocked = options["restricted_cloud_image_models"]
    assert len(blocked) == 1 and blocked[0]["model"] == model
    assert blocked[0]["workspace_allowed"] is False and blocked[0]["can_enable"] is True
    assert blocked[0]["available"] is True
    assert (
        next(n for n in options["nodes"] if n["id"] == blocked[0]["node_id"])[
            "restricted_image_model_count"
        ]
        == 1
    )
    with h.database.sessions() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace is not None and workspace.allowed_models == []
    response = h.client.post(
        "/api/v1/workloads/jobs", headers=headers(h.admin), json=payload(h, connection, provider)
    )
    assert response.status_code == 201
    # Submission may queue, but a restricted model must never be assigned.
    assert h.tick() == 0 and h.poll() is None
    assert h.get(response.json()["id"])["status"] == "PENDING"
    cancelled = h.client.post(
        f"/api/v1/jobs/{response.json()['id']}/cancel", headers=headers(h.admin)
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    response = h.client.post(
        "/api/v1/models/workspace-access",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "node_id": blocked[0]["node_id"],
            "provider_id": blocked[0]["provider_id"],
            "identifier": model,
        },
    )
    assert response.status_code == 200, response.text
    refreshed = h.client.get(path, headers=headers(h.admin)).json()
    assert refreshed["restricted_cloud_image_models"] == []
    assert refreshed["cloud_image_models"][0]["workspace_allowed"] is True
    response = h.client.post(
        "/api/v1/workloads/jobs",
        headers=headers(h.admin),
        json={**payload(h, connection, provider), "paid_consent": False},
    )
    assert response.status_code == 422
    response = h.client.post(
        "/api/v1/workloads/jobs", headers=headers(h.admin), json=payload(h, connection, provider)
    )
    assert response.status_code == 201, response.text
    with h.database.sessions() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace is not None and workspace.allowed_models == [model]
        assert session.scalar(select(ProviderInvocation)) is None
    assert "fixture-only" not in str(options)


def test_restricted_image_inventory_does_not_expose_other_owners_keys_or_allow_member_writes(
    h: Harness,
) -> None:
    _, key_id = enable(h)
    other = provision(h.database, "admin", email="restricted-images-member@example.invalid")
    other_id = UUID(other["owner_id"])
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace is not None
        workspace.allowed_models = []
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=other_id))
    path = f"/api/v1/workloads/options?workspace_id={h.workspace_id}"
    options = h.client.get(path, headers=headers(other)).json()
    assert options["cloud_image_models"] == [] and options["restricted_cloud_image_models"] == []
    # Turn the connection owner into a member of the fixture workspace.
    owner = UUID(h.admin["owner_id"])
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace is not None
        workspace.owner_id = other_id
        membership = session.get(WorkspaceMember, (h.workspace_id, owner))
        if membership:
            membership.role = "member"
        else:
            session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=owner, role="member"))
    options = h.client.get(path, headers=headers(h.admin)).json()
    blocked = options["restricted_cloud_image_models"][0]
    assert blocked["can_enable"] is False
    response = h.client.post(
        "/api/v1/models/workspace-access",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "node_id": blocked["node_id"],
            "provider_id": blocked["provider_id"],
            "identifier": blocked["model"],
        },
    )
    assert response.status_code == 403
    with h.database.sessions.begin() as session:
        key = session.get(AccountProviderKey, key_id)
        assert key is not None
        key.enabled = False
    options = h.client.get(path, headers=headers(h.admin)).json()
    assert options["cloud_image_models"] == [] and options["restricted_cloud_image_models"] == []


def enable(h: Harness, provider: str = "openai") -> tuple[UUID, UUID]:
    owner, node = UUID(h.admin["owner_id"]), UUID(h.workers[0]["credential_id"])
    model = config(provider).model_catalog[0]
    with h.database.sessions.begin() as session:
        key = AccountProviderKey(
            owner_id=owner,
            provider=provider,
            encrypted_key="fixture-only",
            allowed_node_ids=[str(node)],
            model_catalog=[model.model_dump()],
        )
        session.add(key)
        session.flush()
        connection = ProviderConnection(
            owner_id=owner,
            node_id=node,
            provider=provider,
            name="Image fixture",
            account_key_id=key.id,
            policy=ConnectionPolicy(enabled=True, billing="provider").model_dump(),
        )
        session.add(connection)
        session.flush()
        connection_id, key_id = connection.id, key.id
    registration = h.registrations[0].model_copy(
        update={
            "workflow_protocol_version": 1,
            "inference_protocol_version": 1,
            "secondary_capabilities": ["images"],
            "tool_permissions": ["images.generate"],
            "runtimes": ["cloud-images-v1", "account-provider-keys-v1", "provider-connections-v1"],
            "model_deployments": [
                ModelDeployment.model_validate(
                    {
                        "provider_id": "account-images",
                        "provider": provider,
                        "identifier": model.identifier,
                        "connection_id": connection_id,
                        "operations": ["image_generation"],
                    }
                )
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
    return connection_id, key_id


def payload(h: Harness, connection: UUID, provider: str = "openai") -> dict[str, Any]:
    return {
        "workspace_id": str(h.workspace_id),
        "kind": "image",
        "paid_consent": True,
        "connection_id": str(connection),
        "input": {
            "instruction": "Deterministic square fixture",
            "image": {
                "backend": provider,
                "model": config(provider).model_catalog[0].identifier,
                "width": 1024,
                "height": 1024,
            },
        },
    }


def authorize(h: Harness, assignment: dict[str, Any]) -> Any:
    return h.client.post(
        f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/{assignment['job']['id']}/provider/authorize",
        headers=headers(h.workers[0]),
        json={
            "session_id": str(h.registrations[0].session_id),
            "attempt_id": assignment["attempt_id"],
            "fencing_token": assignment["fencing_token"],
            "call_key": "image",
            "input_bytes": 1,
            "max_output_tokens": 1,
        },
    )


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_paid_image_worker_checkpoints_and_downloads_without_text_inference(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    connection, _ = enable(h, provider)
    options = h.client.get(
        f"/api/v1/workloads/options?workspace_id={h.workspace_id}", headers=headers(h.admin)
    ).json()
    assert options["cloud_image_models"][0]["connection_id"] == str(connection)
    assert any(n["cloud_image_models"] for n in options["nodes"])
    response = h.client.post(
        "/api/v1/workloads/jobs", headers=headers(h.admin), json=payload(h, connection, provider)
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["retry"]["limit"] == 0
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None and assignment["deployment"]["operations"] == ["image_generation"]
    calls = []

    async def generate(self: CloudImages, prompt: str, settings: object) -> CloudImageResult:
        with h.database.sessions() as session:
            invocation = session.scalar(select(ProviderInvocation))
            assert invocation is not None and invocation.call_key == "image"
        calls.append(prompt)
        return CloudImageResult([png()], 10, 20)

    monkeypatch.setattr(CloudImages, "generate", generate)
    configured = config(provider)
    configured.connection_id = connection
    asyncio.run(
        execute_agent(
            APIWorkerClient(h),
            UUID(h.workers[0]["credential_id"]),
            h.registrations[0],
            Assignment.model_validate(assignment),
            threading.Event(),
            10,
            [configured],
        )
    )
    assert h.get(job["id"])["status"] == "COMPLETED"
    output = get(h, job["id"], "/result")["output"]
    assert output["kind"] == "image" and len(output["files"]) == 1 and len(calls) == 1
    artifact = get(h, job["id"], "/steps")[0]["output_artifact_id"]
    downloaded = h.client.get(
        f"/api/v1/workloads/jobs/{job['id']}/files/{artifact}/0", headers=headers(h.admin)
    )
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"\x89PNG")
    assert "fixture-image-secret" not in response.text + str(output)
    with h.database.sessions() as session:
        invocation = session.scalar(select(ProviderInvocation))
        assert invocation is not None and invocation.status == "settled"
        assert invocation.usage["input_tokens"] == 10


def test_cloud_image_consent_revocation_replay_and_no_local_fallback(h: Harness) -> None:
    connection, key_id = enable(h)
    body = payload(h, connection)
    for update in ({"paid_consent": False}, {"connection_id": None}):
        response = h.client.post(
            "/api/v1/workloads/jobs", headers=headers(h.admin), json={**body, **update}
        )
        assert response.status_code == 422
    foreign = provision(h.database, "admin", email="image-outsider@example.invalid")
    response = h.client.post("/api/v1/workloads/jobs", headers=headers(foreign), json=body)
    assert response.status_code == 404
    with h.database.sessions.begin() as session:
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=UUID(foreign["owner_id"])))
    # Even a platform administrator in the same workspace cannot borrow this account key.
    response = h.client.post("/api/v1/workloads/jobs", headers=headers(foreign), json=body)
    assert response.status_code == 404
    response = h.client.post("/api/v1/workloads/jobs", headers=headers(h.admin), json=body)
    assert response.status_code == 201, response.text
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    step(h, assignment, "image", 0)
    with h.database.sessions.begin() as session:
        key = session.get(AccountProviderKey, key_id)
        assert key is not None
        key.enabled = False
    assert authorize(h, assignment).status_code in (403, 409)
    with h.database.sessions.begin() as session:
        key = session.get(AccountProviderKey, key_id)
        assert key is not None
        key.enabled = True
    assert authorize(h, assignment).status_code == 200
    assert authorize(h, assignment).status_code == 409
    h.report(assignment, "fail", error_code="provider_timeout")
    assert (
        h.client.post(
            f"/api/v1/jobs/{response.json()['id']}/retry", headers=headers(h.admin)
        ).status_code
        == 409
    )


def test_cloud_call_failure_keeps_marker_and_never_retries(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection, _ = enable(h)
    response = h.client.post(
        "/api/v1/workloads/jobs", headers=headers(h.admin), json=payload(h, connection)
    )
    assert response.status_code == 201
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    calls = []

    async def fail(self: CloudImages, prompt: str, settings: object) -> CloudImageResult:
        calls.append(prompt)
        raise GatewayError("provider_timeout")

    monkeypatch.setattr(CloudImages, "generate", fail)
    configured = config("openai")
    configured.connection_id = connection
    asyncio.run(
        execute_agent(
            APIWorkerClient(h),
            UUID(h.workers[0]["credential_id"]),
            h.registrations[0],
            Assignment.model_validate(assignment),
            threading.Event(),
            10,
            [configured],
        )
    )
    assert h.get(response.json()["id"])["status"] == "FAILED" and len(calls) == 1
    with h.database.sessions() as session:
        invocation = session.scalar(select(ProviderInvocation))
        assert invocation is not None and invocation.status == "reserved"


@pytest.mark.parametrize("missing", ["runtime", "permission", "image_model"])
def test_cloud_route_stays_queued_when_worker_is_incompatible(h: Harness, missing: str) -> None:
    connection, _ = enable(h)
    registration = h.registrations[0]
    if missing == "runtime":
        registration.runtimes = [r for r in registration.runtimes if r != "cloud-images-v1"]
    elif missing == "permission":
        registration.tool_permissions = []
    else:
        registration.model_deployments = []
    registered = h.client.post(
        "/api/v1/workers/register",
        headers=headers(h.workers[0]),
        json=registration.model_dump(mode="json"),
    )
    assert registered.status_code == 200
    response = h.client.post(
        "/api/v1/workloads/jobs", headers=headers(h.admin), json=payload(h, connection)
    )
    assert response.status_code == 201
    assert h.tick() == 0 and h.get(response.json()["id"])["status"] == "PENDING"
