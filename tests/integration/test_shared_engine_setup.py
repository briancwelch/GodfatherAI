"""Durable wizard setup and local-owner approvals against disposable PostgreSQL."""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from godfather_api.models import (
    AccessCredential,
    Job,
    Node,
    SharedEngineConsent,
    SharedEngineSetup,
    Workspace,
    WorkspaceMember,
)
from godfather_api.provision import provision
from godfather_api.shared_engine_setup import managed_permitted
from godfather_contracts import ModelDeployment, SharedInferenceGroup
from godfather_contracts.shared_engine import ACTIVE_PREFIX, SETUP_RUNTIME
from godfather_worker.shared_engine_transport import identity
from sqlalchemy import select

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h

pytestmark = pytest.mark.integration
PREFIX = "/api/v1/workers/shared-engine/"


def api(
    h: Harness, endpoint: str, payload: dict[str, Any], index: int = 0, expected: int = 200
) -> dict[str, Any]:
    result = h.client.post(PREFIX + endpoint, json=payload, headers=headers(h.workers[index]))
    assert result.status_code == expected, result.text
    return dict(result.json())


def capable(h: Harness) -> None:
    for i, registration in enumerate(h.registrations):
        updated = registration.model_copy(
            update={"runtimes": [*registration.runtimes, SETUP_RUNTIME]}
        )
        result = h.client.post(
            "/api/v1/workers/register",
            json=updated.model_dump(mode="json"),
            headers=headers(h.workers[i]),
        )
        assert result.status_code == 200, result.text
        h.registrations[i] = updated


def create(h: Harness, mode: str = "local_network") -> dict[str, Any]:
    return api(
        h,
        "create",
        {
            "workspace_id": str(h.workspace_id),
            "name": "Wizard fixture",
            "model_name": "installed.gguf",
            "mode": mode,
            "node_ids": [
                w["credential_id"] for w in (h.workers[:1] if mode == "single_host" else h.workers)
            ],
        },
        expected=201,
    )


def approve(
    h: Harness, group: dict[str, Any], folder: Path, index: int = 0, **values: Any
) -> dict[str, Any]:
    node = UUID(h.workers[index]["credential_id"])
    gid = UUID(group["proposal"]["id"])
    _, _, pem = identity(folder / str(index), node, gid)
    return api(
        h,
        "approve",
        {
            "group_id": str(gid),
            "devices": [{"id": "CPU", "name": "CPU", "backend": "cpu"}],
            "host": "10.0.0." + str(index + 1),
            "port": 50053,
            "certificate": pem,
            **values,
        },
        index,
    )


def action(
    h: Harness, group: dict[str, Any], verb: str, index: int = 0, expected: int = 200
) -> dict[str, Any]:
    return api(h, "control", {"group_id": group["proposal"]["id"], "action": verb}, index, expected)


def report(h: Harness, group: dict[str, Any], phase: str, index: int, expected: int = 200) -> None:
    api(
        h,
        "report",
        {"group_id": group["proposal"]["id"], "generation": group["generation"], "phase": phase},
        index,
        expected,
    )


def test_owner_approval_start_stop_restart_and_stale_generation(h: Harness, tmp_path: Path) -> None:
    capable(h)
    group = create(h)
    action(h, group, "start", expected=409)
    first = approve(h, group, tmp_path)
    assert not first["group"] and first["members"][1]["certificate"] is None
    group = approve(h, group, tmp_path, 1)
    assert group["group"]["device_count"] == 2
    action(h, group, "start", 1, 403)
    group = action(h, group, "start")
    assert group["desired_running"] and group["generation"] == 1
    report(h, group, "starting", 1)
    report(h, group, "ready", 1)
    with h.database.sessions() as session:
        assert not managed_permitted(session, SharedInferenceGroup.model_validate(group["group"]))
    report(h, group, "starting", 0)
    report(h, group, "ready", 0)
    with h.database.sessions() as session:
        assert managed_permitted(session, SharedInferenceGroup.model_validate(group["group"]))
        row = session.get(SharedEngineSetup, UUID(group["proposal"]["id"]))
        assert row and "model_path" not in str(row.proposal)
    stopped = action(h, group, "stop")
    assert not stopped["desired_running"]
    next_run = action(h, stopped, "start")
    assert next_run["generation"] == 2
    report(h, group, "ready", 0, 409)
    report(h, next_run, "error", 1)
    assert not api(h, "groups", {})["groups"][0]["desired_running"]


def test_an_admin_cannot_approve_another_owners_computer(h: Harness, tmp_path: Path) -> None:
    capable(h)
    second = provision(h.database, "admin", email="second-owner@example.invalid")
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[1]["credential_id"]))
        credential = session.get(AccessCredential, UUID(h.workers[1]["credential_id"]))
        assert node and credential
        node.owner_id = credential.owner_id = UUID(second["owner_id"])
        node.contribution_policy = {"share_with_workspaces": True}
        session.add(
            WorkspaceMember(
                workspace_id=h.workspace_id, user_id=UUID(second["owner_id"]), role="member"
            )
        )
    group = create(h)
    wrong = h.client.post(
        PREFIX + "approve",
        headers=headers(h.admin),
        json={
            "group_id": group["proposal"]["id"],
            "devices": [{"id": "CPU", "name": "CPU", "backend": "cpu"}],
            "host": "10.0.0.2",
            "port": 50053,
            "certificate": "x" * 100,
        },
    )
    assert wrong.status_code == 401
    group = approve(h, group, tmp_path)
    assert [m["approved"] for m in group["members"]] == [True, False]
    group = approve(h, group, tmp_path, 1)
    group = action(h, group, "start")
    group = action(h, group, "withdraw", 1)
    assert not group["desired_running"] and not group["group"]
    assert [m["approved"] for m in group["members"]] == [True, False]
    action(h, group, "start", expected=409)


def test_setup_requires_supported_workers_and_single_host_requires_two_gpus(
    h: Harness, tmp_path: Path
) -> None:
    api(
        h,
        "create",
        {
            "workspace_id": str(h.workspace_id),
            "name": "Missing runtime",
            "model_name": "model.gguf",
            "mode": "single_host",
            "node_ids": [h.workers[0]["credential_id"]],
        },
        expected=409,
    )
    capable(h)
    group = create(h, "single_host")
    node = UUID(h.workers[0]["credential_id"])
    _, _, pem = identity(tmp_path, node, UUID(group["proposal"]["id"]))
    api(
        h,
        "approve",
        {
            "group_id": group["proposal"]["id"],
            "devices": [{"id": "CPU", "name": "CPU", "backend": "cpu"}],
            "host": "127.0.0.1",
            "port": 50053,
            "certificate": pem,
        },
        expected=422,
    )
    devices = [
        {"id": "Vulkan0", "name": "Test GPU A", "backend": "vulkan"},
        {"id": "Vulkan1", "name": "Test GPU B", "backend": "vulkan"},
    ]
    group = approve(h, group, tmp_path, devices=devices)
    assert group["group"]["device_count"] == 2
    assert action(h, group, "start")["desired_running"]


def test_worker_identity_revocation_invalidates_consent_immediately(
    h: Harness, tmp_path: Path
) -> None:
    capable(h)
    group = create(h)
    approve(h, group, tmp_path)
    group = approve(h, group, tmp_path, 1)
    group = action(h, group, "start")
    for index in (0, 1):
        report(h, group, "ready", index)
    topology = SharedInferenceGroup.model_validate(group["group"])
    with h.database.sessions.begin() as session:
        assert managed_permitted(session, topology)
        credential = session.get(AccessCredential, UUID(h.workers[1]["credential_id"]))
        assert credential
        credential.revoked = True
    with h.database.sessions() as session:
        assert not managed_permitted(session, topology)
    assert api(h, "groups", {})["groups"][0]["group"] is None


def test_competing_groups_cannot_reserve_the_same_computers(h: Harness, tmp_path: Path) -> None:
    capable(h)
    first, second = create(h), create(h)
    for group in (first, second):
        approve(h, group, tmp_path)
        approve(h, group, tmp_path, 1)
    running = action(h, first, "start")
    assert action(h, running, "start")["generation"] == running["generation"]
    action(h, second, "start", expected=409)


@pytest.mark.parametrize("operation,index", [("withdraw", 1), ("delete", 0), ("delete", 1)])
def test_shared_session_does_not_accept_ordinary_jobs_and_revocation_fences_result(
    h: Harness, tmp_path: Path, operation: str, index: int
) -> None:
    capable(h)
    group = create(h)
    approve(h, group, tmp_path)
    group = approve(h, group, tmp_path, 1)
    group = action(h, group, "start")
    topology = SharedInferenceGroup.model_validate(group["group"])
    model = ModelDeployment(
        provider_id="shared-fixture",
        provider="openai_compatible",
        identifier=topology.model,
        shared_inference_group_id=topology.id,
        operations=["chat", "stream"],
    )
    for i in (0, 1):
        report(h, group, "starting", i)
        report(h, group, "ready", i)
        registration = h.registrations[i].model_copy(
            update={
                "session_id": uuid4(),
                "inference_protocol_version": 1,
                "shared_inference_groups": [topology],
                "model_deployments": [model] if i == 0 else [],
                "runtimes": [SETUP_RUNTIME, ACTIVE_PREFIX + str(topology.id)],
            }
        )
        result = h.client.post(
            "/api/v1/workers/register",
            headers=headers(h.workers[i]),
            json=registration.model_dump(mode="json"),
        )
        assert result.status_code == 200, result.text
        h.registrations[i] = registration
    ordinary = h.submit()
    # Managed engines use a generated alias, separate from the installed model's name.
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        workspace.allowed_models = ["installed.gguf"]
    options = h.client.get(
        "/api/v1/shared-inference/options",
        headers=headers(h.admin),
        params={"workspace_id": str(h.workspace_id)},
    ).json()["groups"]
    assert len(options) == 1 and options[0]["workspace_allowed"] is False
    enabled = h.client.post(
        "/api/v1/shared-inference/workspace-access",
        headers=headers(h.admin),
        json={"workspace_id": str(h.workspace_id), "group_id": str(topology.id)},
    )
    assert enabled.status_code == 200, enabled.text
    assert h.tick() == 0 and h.get(ordinary["id"])["status"] == "PENDING"
    from tests.integration.test_inference import inference_result
    from tests.integration.test_shared_inference import submit

    job = submit(h, topology)
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    if operation == "delete":
        api(h, "delete", {"group_id": group["proposal"]["id"]}, index)
    else:
        action(h, group, "withdraw", index)
    h.report(assignment, "complete", expected=409, result=inference_result(model))
    h.tick()
    assert h.get(job["id"])["status"] == "FAILED"


def test_initiator_delete_is_durable_idempotent_and_keeps_history_and_identity(
    h: Harness, tmp_path: Path
) -> None:
    capable(h)
    group = create(h)
    approve(h, group, tmp_path)
    group = approve(h, group, tmp_path, 1)
    group = action(h, group, "start")
    for index in (0, 1):
        report(h, group, "ready", index)
    topology = SharedInferenceGroup.model_validate(group["group"])
    job = h.submit()
    payload = {"group_id": group["proposal"]["id"]}
    assert api(h, "delete", payload) == {"removed": True, "scope": "setup"}
    assert api(h, "delete", payload) == {"removed": True, "scope": "setup"}
    for index in (0, 1):
        assert not api(h, "groups", {}, index)["groups"]
        action(h, group, "start", index, 409)
        report(h, group, "ready", index, 409)
        report(h, group, "stopped", index)
    with h.database.sessions() as session:
        row = session.get(SharedEngineSetup, UUID(payload["group_id"]))
        assert row and row.deleted_at is not None and not row.desired_running
        assert not managed_permitted(session, topology)
        for node_id in group["proposal"]["node_ids"]:
            consent = session.get(SharedEngineConsent, (row.id, UUID(node_id)))
            assert consent and consent.dismissed and not consent.approved
            assert not consent.configuration
            node = session.get(Node, UUID(node_id))
            assert node and node.name and node.owner_id == UUID(h.admin["owner_id"])
        assert session.get(Job, UUID(job["id"])) is not None


def test_participant_delete_only_removes_own_invitation_and_cannot_be_reapproved(
    h: Harness, tmp_path: Path
) -> None:
    capable(h)
    group = create(h)
    approve(h, group, tmp_path)
    group = approve(h, group, tmp_path, 1)
    payload = {"group_id": group["proposal"]["id"]}
    assert api(h, "delete", payload, 1) == {"removed": True, "scope": "computer"}
    assert api(h, "delete", payload, 1) == {"removed": True, "scope": "computer"}
    assert not api(h, "groups", {}, 1)["groups"]
    remaining = api(h, "groups", {})["groups"]
    assert len(remaining) == 1 and remaining[0]["group"] is None
    assert [m["approved"] for m in remaining[0]["members"]] == [True, False]
    action(h, group, "start", expected=409)
    api(
        h,
        "approve",
        {
            **payload,
            "devices": [{"id": "CPU", "name": "CPU", "backend": "cpu"}],
            "host": "10.0.0.2",
            "port": 50053,
            "certificate": "x" * 100,
        },
        1,
        409,
    )
    with h.database.sessions() as session:
        row = session.get(SharedEngineSetup, UUID(payload["group_id"]))
        assert row and row.deleted_at is None
    # The initiating computer may still delete its whole setup.
    assert api(h, "delete", payload)["scope"] == "setup"
    assert not api(h, "groups", {})["groups"]


def test_nonparticipant_and_admin_session_cannot_delete_another_computers_setup(h: Harness) -> None:
    capable(h)
    group = create(h, "single_host")
    payload = {"group_id": group["proposal"]["id"]}
    api(h, "delete", payload, 1, 404)
    result = h.client.post(PREFIX + "delete", json=payload, headers=headers(h.admin))
    assert result.status_code == 401
    assert len(api(h, "groups", {})["groups"]) == 1


def test_deleted_invitations_free_capacity_and_do_not_displace_visible_setups(h: Harness) -> None:
    capable(h)
    for _ in range(10):
        group = create(h)
        api(h, "delete", {"group_id": group["proposal"]["id"]})
    remaining = create(h)
    for index in (0, 1):
        visible = api(h, "groups", {}, index)["groups"]
        assert [g["proposal"]["id"] for g in visible] == [remaining["proposal"]["id"]]


def test_starting_never_resets_a_live_attempt(h: Harness, tmp_path: Path) -> None:
    capable(h)
    group = create(h)
    approve(h, group, tmp_path)
    approve(h, group, tmp_path, 1)
    job = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    group = action(h, group, "start")
    report(h, group, "starting", 0, 409)
    with h.database.sessions() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node and node.session_id == h.registrations[0].session_id
        assert session.scalar(select(Job.status).where(Job.id == UUID(job["id"]))) == "RUNNING"


@pytest.mark.parametrize("state", ["draining", "disabled"])
def test_initiator_cannot_override_owner_draining_or_disabled_state(
    h: Harness, tmp_path: Path, state: str
) -> None:
    capable(h)
    group = create(h)
    approve(h, group, tmp_path)
    approve(h, group, tmp_path, 1)
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[1]["credential_id"]))
        assert node
        node.state = state
    action(h, group, "start", expected=409)
