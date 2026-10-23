"""Real PostgreSQL membership sharing without worker-side identity lists."""

from uuid import UUID, uuid4

import pytest
from godfather_api.models import Job, Node, Workspace, WorkspaceMember
from godfather_api.provision import provision
from godfather_api.scheduler import permitted
from godfather_contracts.jobs import Requirements

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h

pytestmark = pytest.mark.integration


def test_joined_workspace_enables_ordinary_jobs_and_leaving_revokes_active_reports(
    h: Harness,
) -> None:
    owner = provision(h.database, "admin", email="contributor@example.invalid")
    owner_id = UUID(owner["owner_id"])
    worker = provision(h.database, "worker", owner_id=owner_id, name="Member computer")
    registration = h.registrations[1].model_copy(
        update={
            "session_id": uuid4(),
            "share_with_workspaces": True,
            "scheduling_policy": "shared",
        }
    )
    response = h.client.post(
        "/api/v1/workers/register",
        headers=headers(worker),
        json=registration.model_dump(mode="json"),
    )
    assert response.status_code == 200
    h.workers.append(worker)
    h.registrations.append(registration)
    with h.database.sessions.begin() as session:
        for old in h.workers[:2]:
            node = session.get(Node, UUID(old["credential_id"]))
            assert node
            node.state = "disabled"
        node = session.get(Node, UUID(worker["credential_id"]))
        assert node and node.contribution_policy == {"share_with_workspaces": True}
    job = h.submit()
    assert h.tick() == 0  # Admins cannot borrow a non-member's computer.
    with h.database.sessions.begin() as session:
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=owner_id, role="member"))
    assert h.tick() == 1  # No worker restart or user/workspace IDs required.
    assignment = h.poll(2)
    assert assignment and assignment["job"]["id"] == job["id"]
    h.start(assignment, 2)
    with h.database.sessions.begin() as session:
        membership = session.get(WorkspaceMember, (h.workspace_id, owner_id))
        assert membership
        session.delete(membership)
    response = h.client.post(
        f"/api/v1/workers/{worker['credential_id']}/jobs/{job['id']}/report",
        headers=headers(worker),
        json={
            "session_id": str(registration.session_id),
            "attempt_id": assignment["attempt_id"],
            "fencing_token": assignment["fencing_token"],
            "action": "progress",
            "progress": 10,
        },
    )
    assert response.status_code in (403, 409)
    with h.database.sessions.begin() as session:
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=owner_id, role="member"))
        node = session.get(Node, UUID(worker["credential_id"]))
        stored = session.get(Job, UUID(job["id"]))
        assert node and stored and permitted(session, stored, node)
        node.scheduling_policy = "dedicated"
        assert not permitted(session, stored, node)  # Local opt-out wins over membership.
        node.scheduling_policy = "shared"
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        stored.requirements = Requirements.model_validate(
            {"models": [{"runtime": "ollama", "identifier": "fixture"}]}
        ).model_dump(mode="json")
        workspace.allowed_models = ["fixture"]
        assert permitted(session, stored, node)
        workspace.allowed_models = []
        assert not permitted(session, stored, node)
        workspace.allowed_models = None
        stored.requirements = Requirements.model_validate(
            {
                "model_selection": {
                    "provider": "openai",
                    "connection_id": str(uuid4()),
                    "identifier": "paid-model",
                    "paid_consent": True,
                }
            }
        ).model_dump(mode="json")
        assert not permitted(session, stored, node)  # Compute sharing never grants paid keys.


def test_new_workspaces_follow_membership_and_old_registration_withdraws_opt_in(h: Harness) -> None:
    consumer = provision(h.database, "admin", email="new-member@example.invalid")
    consumer_id = UUID(consumer["owner_id"])
    registration = h.registrations[0].model_copy(
        update={"share_with_workspaces": True, "scheduling_policy": "shared"}
    )
    response = h.client.post(
        "/api/v1/workers/register",
        headers=headers(h.workers[0]),
        json=registration.model_dump(mode="json"),
    )
    assert response.status_code == 200
    with h.database.sessions.begin() as session:
        workspace = Workspace(owner_id=consumer_id, name="Joined after worker registration")
        session.add(workspace)
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id, user_id=UUID(h.admin["owner_id"]), role="member"
            )
        )
        session.flush()
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node
        probe = Job(
            owner_id=consumer_id,
            workspace_id=workspace.id,
            type="agent.workflow",
            requirements={},
            input_refs={},
        )
        assert permitted(session, probe, node)
    # An old/withdrawn registration must clear the flag, not preserve a stale grant.
    response = h.client.post(
        "/api/v1/workers/register",
        headers=headers(h.workers[0]),
        json=h.registrations[0].model_dump(mode="json"),
    )
    assert response.status_code == 200
    with h.database.sessions() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node and node.contribution_policy == {}
