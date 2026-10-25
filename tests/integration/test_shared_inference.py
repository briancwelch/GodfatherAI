"""Real PostgreSQL shared-engine reservations, consent, restart and fencing.

Model math is a controlled provider response, not physical multi-GPU evidence.
"""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.models import AccessCredential, Attempt, Event, Node, Workspace, WorkspaceMember
from godfather_api.provision import provision
from godfather_contracts import GPU, ModelDeployment, SharedInferenceGroup
from godfather_contracts.jobs import Assignment
from godfather_contracts.shared_engine import ACTIVE_PREFIX
from godfather_model_gateway import ProviderConfig
from godfather_worker.inference import execute_inference
from sqlalchemy import select

from tests.integration.test_distributed import RecordingModel
from tests.integration.test_inference import APIWorkerClient, inference_result
from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h

pytestmark = pytest.mark.integration


def configure(
    h: Harness, mode: str = "local_network"
) -> tuple[SharedInferenceGroup, ModelDeployment]:
    members = [UUID(worker["credential_id"]) for worker in h.workers]
    group = SharedInferenceGroup.model_validate(
        {
            "id": uuid4(),
            "name": "Private test engine",
            "mode": mode,
            "leader_node_id": members[0],
            "node_ids": members[:1] if mode == "single_host" else members,
            "model": "shared-fixture",
            "engine": "llama_cpp",
            "parallelism": "pipeline",
            "device_count": max(2, len(members)),
            "private_transport": True,
        }
    )
    model = ModelDeployment(
        provider_id="shared-local",
        provider="openai_compatible",
        identifier=group.model,
        shared_inference_group_id=group.id,
        operations=["chat", "stream"],
    )
    for i in range(len(members)):
        resource = h.registrations[i].resources.model_copy(
            update={
                "gpus": [
                    GPU(name="Fixture GPU A", backend="cuda"),
                    GPU(name="Fixture GPU B", backend="cuda"),
                ]
            }
        )
        registration = h.registrations[i].model_copy(
            update={
                "inference_protocol_version": 1,
                "resources": resource,
                "model_deployments": [model] if i == 0 else [],
                "shared_inference_groups": [group] if members[i] in group.node_ids else [],
            }
        )
        r = h.client.post(
            "/api/v1/workers/register",
            headers=headers(h.workers[i]),
            json=registration.model_dump(mode="json"),
        )
        assert r.status_code == 200, r.text
        h.registrations[i] = registration
    return group, model


def submit(h: Harness, group: SharedInferenceGroup, **values: object) -> dict[str, Any]:
    r = h.client.post(
        "/api/v1/shared-inference/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "group_id": str(group.id),
            "prompt": "Add 1+1",
            "wide_area_consent": group.mode == "wide_area",
            **values,
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


@pytest.mark.parametrize("mode", ["single_host", "local_network", "wide_area"])
def test_one_request_for_each_topology_through_worker_and_durable_result(
    h: Harness, mode: str
) -> None:
    group, model = configure(h, mode)
    options = h.client.get(
        "/api/v1/shared-inference/options",
        params={"workspace_id": str(h.workspace_id)},
        headers=headers(h.admin),
    ).json()
    assert options["groups"][0]["available"] is True
    job = submit(h, group)
    assert h.tick() == 1
    assignment = h.poll(0)
    assert assignment and h.poll(1) is None
    provider = RecordingModel("2")
    asyncio.run(
        execute_inference(
            APIWorkerClient(h),
            group.leader_node_id,
            h.registrations[0],
            Assignment.model_validate(assignment),
            threading.Event(),
            10,
            [
                ProviderConfig(
                    id="shared-local",
                    provider="openai_compatible",
                    shared_inference_group_id=group.id,
                    url="http://127.0.0.1:18080/v1",
                )
            ],
            provider,
        )
    )
    assert provider.calls == ["shared-fixture"] and provider.prompts == ["Add 1+1"]
    assert h.get(job["id"])["status"] == "COMPLETED"
    with h.database.sessions() as session:
        attempt = session.get(Attempt, UUID(assignment["attempt_id"]))
        assert attempt
        sessions = attempt.result["shared_sessions"]
        assert isinstance(sessions, dict)
        assert set(sessions) == {str(member) for member in group.node_ids}
    assert "shared_sessions" not in h.get(job["id"])["result"]
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as client:
        r = client.get(
            "/api/v1/shared-inference/jobs",
            params={"workspace_id": str(h.workspace_id)},
            headers=headers(h.admin),
        )
        assert r.status_code == 200 and r.json()["items"][0]["result"]["text"] == "2"
    # Ordinary model selection cannot silently route to the shared group.
    assert (
        h.client.get(
            "/api/v1/models", params={"workspace_id": str(h.workspace_id)}, headers=headers(h.admin)
        ).json()
        == []
    )


def test_all_members_reserved_and_second_group_waits_until_first_finishes(h: Harness) -> None:
    group, model = configure(h)
    first, second = submit(h, group), submit(h, group)
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment and assignment["job"]["id"] == first["id"]
    h.submit()
    assert h.tick() == 0 and h.poll(1) is None
    h.start(assignment)
    h.report(assignment, "complete", result=inference_result(model))
    assert h.tick() >= 1
    assert h.get(second["id"])["status"] in ("PENDING", "ASSIGNED")


@pytest.mark.parametrize(
    "loss", ["consent", "offline", "session", "credential", "disabled", "engine"]
)
def test_member_loss_rejects_late_completion_and_ends_attempt(h: Harness, loss: str) -> None:
    group, model = configure(h)
    job = submit(h, group)
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    with h.database.sessions.begin() as session:
        member = session.get(Node, group.node_ids[1])
        assert member
        if loss == "consent":
            member.runtimes = {**member.runtimes, "shared_inference_groups": []}
        elif loss == "offline":
            member.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=60)
        elif loss == "session":
            member.session_id = uuid4()
        elif loss == "engine":
            leader = session.get(Node, group.leader_node_id)
            assert leader
            leader.runtimes = {**leader.runtimes, "model_deployments": []}
        elif loss == "disabled":
            member.state = "disabled"
        else:
            credential = session.scalar(
                select(AccessCredential).where(AccessCredential.node_id == member.id)
            )
            assert credential
            credential.revoked = True
    h.report(assignment, "complete", expected=409, result=inference_result(model))
    h.tick()
    assert h.get(job["id"])["status"] == "FAILED"
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin)).status_code
        == 409
    )


def test_private_groups_and_explicit_wide_area_consent(h: Harness) -> None:
    group, _ = configure(h, "wide_area")
    r = h.client.post(
        "/api/v1/shared-inference/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "group_id": str(group.id),
            "prompt": "Test",
            "wide_area_consent": False,
        },
    )
    assert r.status_code == 422
    other = provision(h.database, "admin", email="shared-private@example.invalid")
    assert (
        h.client.get(
            "/api/v1/shared-inference/options",
            params={"workspace_id": str(h.workspace_id)},
            headers=headers(other),
        ).status_code
        == 404
    )
    with h.database.sessions.begin() as session:
        member = session.get(Node, group.node_ids[1])
        assert member
        member.owner_id = UUID(other["owner_id"])
        session.add(
            WorkspaceMember(workspace_id=h.workspace_id, user_id=member.owner_id, role="member")
        )
        member.contribution_policy = {"allowed_job_owner_ids": [], "allowed_workspace_ids": []}
    assert (
        h.client.get(
            "/api/v1/shared-inference/options",
            params={"workspace_id": str(h.workspace_id)},
            headers=headers(h.admin),
        ).json()["groups"]
        == []
    )


@pytest.mark.parametrize("existing_models", [[], ["qwen3:8b", "existing-local-model"]])
def test_restricted_group_is_discoverable_and_explicit_grant_preserves_policy(
    h: Harness, existing_models: list[str]
) -> None:
    group, _ = configure(h)
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        workspace.allowed_models = existing_models
        workspace.allowed_tools = ["plan.describe@1"]
        for member_id in group.node_ids:
            member = session.get(Node, member_id)
            assert member
            runtimes = member.runtimes.get("runtimes", [])
            assert isinstance(runtimes, list)
            member.runtimes = {
                **member.runtimes,
                "runtimes": [*runtimes, ACTIVE_PREFIX + str(group.id)],
            }
    response = h.client.get(
        "/api/v1/shared-inference/options",
        params={"workspace_id": str(h.workspace_id)},
        headers=headers(h.admin),
    )
    assert response.status_code == 200, response.text
    entry = response.json()["groups"][0]
    assert entry["id"] == str(group.id)
    assert entry["workspace_allowed"] is False and entry["available"] is False
    assert entry["can_enable"] is True and entry["model_discovered"] is True
    assert "Workspace permission required" in entry["reason"]
    denied = h.client.post(
        "/api/v1/shared-inference/jobs",
        headers=headers(h.admin),
        json={"workspace_id": str(h.workspace_id), "group_id": str(group.id), "prompt": "Test"},
    )
    assert denied.status_code == 409
    payload = {"workspace_id": str(h.workspace_id), "group_id": str(group.id)}
    for _ in range(2):
        enabled = h.client.post(
            "/api/v1/shared-inference/workspace-access", headers=headers(h.admin), json=payload
        )
        assert enabled.status_code == 200 and enabled.json() == {"enabled": True}
    with h.database.sessions() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        assert workspace.allowed_models == [*existing_models, group.model]
        assert workspace.allowed_tools == ["plan.describe@1"]
        events = list(
            session.scalars(
                select(Event).where(
                    Event.workspace_id == h.workspace_id,
                    Event.type == "security.workspace_model_enabled",
                )
            )
        )
        assert len(events) == 1
        assert events[0].details["shared_inference_group_id"] == str(group.id)
    refreshed = h.client.get(
        "/api/v1/shared-inference/options",
        params={"workspace_id": str(h.workspace_id)},
        headers=headers(h.admin),
    ).json()["groups"][0]
    assert refreshed["workspace_allowed"] is True and refreshed["available"] is True
    job = submit(h, group)
    assert h.tick() == 1 and h.get(job["id"])["status"] == "ASSIGNED"
    # A later administrator revocation is still enforced on the selected group.
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        workspace.allowed_models = existing_models
    assert h.poll() is None


@pytest.mark.parametrize("role", ["member", "admin"])
def test_shared_model_grant_requires_workspace_administration(h: Harness, role: str) -> None:
    group, _ = configure(h)
    other = provision(h.database, "admin", email="shared-model-reviewer@example.invalid")
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        workspace.allowed_models = []
        session.add(
            WorkspaceMember(workspace_id=h.workspace_id, user_id=UUID(other["owner_id"]), role=role)
        )
        for member_id in group.node_ids:
            member = session.get(Node, member_id)
            assert member
            member.scheduling_policy = "shared"
            member.contribution_policy = {"share_with_workspaces": True}
    entry = h.client.get(
        "/api/v1/shared-inference/options",
        params={"workspace_id": str(h.workspace_id)},
        headers=headers(other),
    ).json()["groups"][0]
    assert entry["can_enable"] is (role == "admin")
    result = h.client.post(
        "/api/v1/shared-inference/workspace-access",
        headers=headers(other),
        json={"workspace_id": str(h.workspace_id), "group_id": str(group.id)},
    )
    assert result.status_code == (200 if role == "admin" else 403), result.text
    with h.database.sessions() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        assert workspace.allowed_models == ([group.model] if role == "admin" else [])


@pytest.mark.parametrize("blocker", ["unknown_group", "missing_model", "wrong_binding", "limit"])
def test_shared_model_grant_rejects_stale_identity_and_full_policy(
    h: Harness, blocker: str
) -> None:
    group, _ = configure(h)
    existing = [f"existing-{i}" for i in range(64)] if blocker == "limit" else []
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        workspace.allowed_models = existing
        if blocker in ("missing_model", "wrong_binding"):
            leader = session.get(Node, group.leader_node_id)
            assert leader
            deployments = leader.runtimes["model_deployments"]
            assert isinstance(deployments, list)
            if blocker == "wrong_binding":
                deployments = [{**deployments[0], "shared_inference_group_id": str(uuid4())}]
            else:
                deployments = []
            leader.runtimes = {**leader.runtimes, "model_deployments": deployments}
    result = h.client.post(
        "/api/v1/shared-inference/workspace-access",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "group_id": str(uuid4() if blocker == "unknown_group" else group.id),
        },
    )
    assert result.status_code == (404 if blocker == "unknown_group" else 409), result.text
    with h.database.sessions() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace and workspace.allowed_models == existing


def test_shared_model_grant_cannot_override_node_owner_or_private_workspace(h: Harness) -> None:
    group, _ = configure(h)
    outsider = provision(h.database, "admin", email="shared-model-outsider@example.invalid")
    payload = {"workspace_id": str(h.workspace_id), "group_id": str(group.id)}
    endpoint = "/api/v1/shared-inference/workspace-access"
    assert h.client.post(endpoint, json=payload).status_code == 401
    assert h.client.post(endpoint, json=payload, headers=headers(h.workers[0])).status_code == 401
    assert h.client.post(endpoint, json=payload, headers=headers(outsider)).status_code == 404
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        workspace.allowed_models = []
        member = session.get(Node, group.node_ids[1])
        assert member
        member.owner_id = UUID(outsider["owner_id"])
        member.contribution_policy = {"allowed_job_owner_ids": [], "allowed_workspace_ids": []}
        session.add(
            WorkspaceMember(workspace_id=h.workspace_id, user_id=member.owner_id, role="member")
        )
    denied = h.client.post(endpoint, json=payload, headers=headers(h.admin))
    assert denied.status_code == 404, denied.text
    with h.database.sessions() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace and workspace.allowed_models == []


def test_locked_leader_cannot_release_active_group_peer_reservations(h: Harness) -> None:
    group, _ = configure(h)
    submit(h, group)
    assert h.tick() == 1
    h.submit()
    with h.database.sessions.begin() as session:
        session.scalar(select(Node).where(Node.id == group.leader_node_id).with_for_update())
        assert h.tick() == 0
    assert h.poll(1) is None


def test_cancellation_remains_cancelled_when_group_disconnects(h: Harness) -> None:
    group, _ = configure(h)
    job = submit(h, group)
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)).status_code
        == 200
    )
    with h.database.sessions.begin() as session:
        member = session.get(Node, group.node_ids[1])
        assert member
        member.state = "offline"
    h.tick()
    assert h.get(job["id"])["status"] == "CANCELLED"


def test_three_computers_share_one_job_with_one_leader_assignment(h: Harness) -> None:
    worker = provision(
        h.database, "worker", owner_id=UUID(h.admin["owner_id"]), name="Third participant"
    )
    registration = h.registrations[1].model_copy(update={"session_id": uuid4()})
    assert (
        h.client.post(
            "/api/v1/workers/register",
            headers=headers(worker),
            json=registration.model_dump(mode="json"),
        ).status_code
        == 200
    )
    h.workers.append(worker)
    h.registrations.append(registration)
    group, _ = configure(h)
    job = submit(h, group)
    assert h.tick() == 1
    assignment = h.poll(0)
    assert assignment and assignment["job"]["id"] == job["id"]
    assert h.poll(1) is None and h.poll(2) is None


def test_group_respects_preferred_peer_owners_waiting_work(h: Harness) -> None:
    group, _ = configure(h)
    other = provision(h.database, "admin", email="preferred-peer@example.invalid")
    with h.database.sessions.begin() as session:
        member = session.get(Node, group.node_ids[1])
        assert member
        member.owner_id = UUID(other["owner_id"])
        member.scheduling_policy = "preferred"
        member.contribution_policy = {"share_with_workspaces": True}
        session.add(
            WorkspaceMember(workspace_id=h.workspace_id, user_id=member.owner_id, role="member")
        )
    group_job = submit(h, group)
    owner_job = h.client.post(
        "/api/v1/jobs",
        headers=headers(other),
        json={"workspace_id": str(h.workspace_id), "requirements": {"os": "macos"}},
    )
    assert owner_job.status_code == 201, owner_job.text
    assert h.tick() == 1
    assert h.get(group_job["id"])["status"] == "PENDING"
    assignment = h.poll(1)
    assert assignment and assignment["job"]["id"] == owner_job.json()["id"]
