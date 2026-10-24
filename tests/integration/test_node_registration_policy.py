"""Durable role switches apply at every creation boundary without retiring existing nodes."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from godfather_api.app import create_app
from godfather_api.models import Event, Node
from godfather_contracts import Heartbeat, Registration
from godfather_worker.desktop import Pairing
from godfather_worker.simulated import profile
from sqlalchemy import select

from tests.integration.test_authentication import AuthHarness
from tests.integration.test_authentication import auth as auth
from tests.integration.test_nodes import database as database
from tests.integration.test_worker_enrollment import exchange

pytestmark = pytest.mark.integration
POLICY = "administration/node-registration"
RESTRICTED = {"members_can_add_nodes": False, "contributors_can_add_nodes": False}


@pytest.mark.parametrize("role", ["member", "contributor"])
def test_role_switches_persist_and_block_each_new_node_boundary(
    auth: AuthHarness, role: str
) -> None:
    assert auth.login(auth.client).status_code == 303
    member = auth.browser()
    invitation = auth.invite("owner@example.invalid", [role])
    assert auth.login(member, "owner-sub", "owner@example.invalid", invitation).status_code == 303
    assert "nodes.add" in member.get("/api/v1/auth/me").json()["permissions"]
    assert member.get("/api/v1/" + POLICY).status_code == 403
    assert auth.post(member, POLICY, RESTRICTED).status_code == 403
    assert auth.client.post("/api/v1/" + POLICY, json=RESTRICTED).status_code == 403
    assert auth.post(auth.client, POLICY, {**RESTRICTED, "extra": True}).status_code == 422
    assert (
        auth.post(auth.client, POLICY, {**RESTRICTED, "members_can_add_nodes": "false"}).status_code
        == 422
    )

    pending = Pairing()
    assert (
        auth.post(
            member,
            "administration/worker-enrollments",
            {"name": "Pending", "challenge": pending.challenge},
        ).status_code
        == 201
    )
    manual = auth.post(member, "administration/node-credentials", {"name": "Manual"}).json()
    assert auth.post(auth.client, POLICY, RESTRICTED).json() == RESTRICTED
    account = member.get("/api/v1/auth/me").json()
    assert (
        "nodes.add" not in account["permissions"] and "nodes.contribute" in account["permissions"]
    )
    assert (
        auth.post(member, "administration/node-credentials", {"name": "Blocked"}).status_code == 403
    )
    assert (
        auth.post(
            member,
            "administration/worker-enrollments",
            {"name": "Blocked", "challenge": Pairing().challenge},
        ).status_code
        == 403
    )
    assert exchange(auth, pending).status_code == 403
    registration = Registration(**profile("LA-01").model_dump(), session_id=uuid4())
    assert (
        auth.client.post(
            "/api/v1/workers/register",
            json=registration.model_dump(mode="json"),
            headers={"Authorization": "Bearer " + manual["token"]},
        ).status_code
        == 403
    )
    # Admins remain allowed, including when they have another restricted role.
    assert "nodes.add" in auth.client.get("/api/v1/auth/me").json()["permissions"]
    assert (
        auth.post(
            auth.client, "administration/node-credentials", {"name": "Admin computer"}
        ).status_code
        == 201
    )
    with TestClient(create_app(auth.settings)) as restarted:
        restarted.cookies.update(auth.client.cookies)
        assert restarted.get("/api/v1/" + POLICY).json() == RESTRICTED
    current = {
        **RESTRICTED,
        "contributors_can_add_nodes" if role == "contributor" else "members_can_add_nodes": True,
    }
    assert auth.post(auth.client, POLICY, current).status_code == 200
    assert "nodes.add" in member.get("/api/v1/auth/me").json()["permissions"]
    assert exchange(auth, pending).status_code == 200
    with auth.database.sessions() as session:
        event = session.scalar(
            select(Event).where(Event.type == "security.node_registration_policy_updated")
        )
        assert event is not None and event.details["after"] == RESTRICTED


def test_existing_member_node_heartbeat_and_identity_reconnect_survive_admin_only_policy(
    auth: AuthHarness,
) -> None:
    assert auth.login(auth.client).status_code == 303
    member = auth.browser()
    invitation = auth.invite("owner@example.invalid", ["member"])
    assert auth.login(member, "owner-sub", "owner@example.invalid", invitation).status_code == 303
    pairing = Pairing()
    payload = {"name": "Keep name and history", "challenge": pairing.challenge}
    assert auth.post(member, "administration/worker-enrollments", payload).status_code == 201
    credential = exchange(auth, pairing).json()
    headers = {"Authorization": "Bearer " + pairing.machine_secret}
    registration = Registration(**profile("LA-01").model_dump(), session_id=uuid4())
    result = member.post(
        "/api/v1/workers/register", json=registration.model_dump(mode="json"), headers=headers
    )
    assert result.status_code == 200, result.text
    node_id = result.json()["node_id"]
    assert auth.post(auth.client, POLICY, RESTRICTED).status_code == 200
    heartbeat = Heartbeat(session_id=registration.session_id, resources=registration.resources)
    assert (
        member.post(
            f"/api/v1/workers/{node_id}/heartbeat",
            json=heartbeat.model_dump(mode="json"),
            headers=headers,
        ).status_code
        == 200
    )
    with auth.database.sessions.begin() as session:
        node = session.get(Node, UUID(node_id))
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
    replacement = Pairing()
    assert (
        auth.post(
            member,
            "administration/worker-enrollments",
            {**payload, "challenge": replacement.challenge, "reconnect": True},
        ).status_code
        == 201
    )
    exchanged = exchange(auth, replacement)
    assert exchanged.status_code == 200, exchanged.text
    replaced = member.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers={"Authorization": "Bearer " + replacement.machine_secret},
    )
    assert replaced.status_code == 200 and replaced.json()["node_id"] == credential["credential_id"]
    with auth.database.sessions() as session:
        node = session.get(Node, UUID(node_id))
        assert node is not None and node.name == "Keep name and history"


def test_unregistered_credential_cannot_bypass_policy_by_selecting_reconnect(
    auth: AuthHarness,
) -> None:
    assert auth.login(auth.client).status_code == 303
    member = auth.browser()
    invitation = auth.invite("owner@example.invalid", ["member"])
    assert auth.login(member, "owner-sub", "owner@example.invalid", invitation).status_code == 303
    assert (
        auth.post(member, "administration/node-credentials", {"name": "Not registered"}).status_code
        == 201
    )
    assert auth.post(auth.client, POLICY, RESTRICTED).status_code == 200
    response = auth.post(
        member,
        "administration/worker-enrollments",
        {"name": "Not registered", "challenge": Pairing().challenge, "reconnect": True},
    )
    assert response.status_code == 403
