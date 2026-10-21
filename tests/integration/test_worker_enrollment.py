"""Real PostgreSQL pairing, Google identity, concurrency and v1 protocol integration.

Only Google's upstream exchange is mocked by the existing OIDC test harness.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from godfather_api.models import (
    AccessCredential,
    Attempt,
    Event,
    GoogleIdentity,
    Job,
    Node,
    User,
    WorkerEnrollment,
    Workspace,
)
from godfather_contracts import Heartbeat, Registration
from godfather_worker.desktop import Pairing
from godfather_worker.simulated import profile
from sqlalchemy import delete, select

from tests.integration.test_authentication import AuthHarness
from tests.integration.test_authentication import auth as auth
from tests.integration.test_nodes import database as database

pytestmark = pytest.mark.integration


def approve(auth: AuthHarness, pairing: Pairing) -> None:
    assert auth.login(auth.client).status_code == 303
    response = auth.post(
        auth.client,
        "administration/worker-enrollments",
        {
            "challenge": pairing.challenge,
            "name": "Remote Mac",
        },
    )
    assert response.status_code == 201, response.text


def exchange(auth: AuthHarness, pairing: Pairing) -> Any:
    return auth.client.post("/api/v1/workers/enrollment/exchange", json=pairing.model_dump())


def test_pairing_requires_google_owner_and_consumes_once_with_existing_protocol(
    auth: AuthHarness,
) -> None:
    pairing = Pairing()
    assert (
        auth.post(
            auth.client,
            "administration/worker-enrollments",
            {
                "challenge": pairing.challenge,
                "name": "Remote Mac",
            },
        ).status_code
        == 401
    )
    assert exchange(auth, pairing).status_code == 404
    approve(auth, pairing)
    response = exchange(auth, pairing)
    assert response.status_code == 200, response.text
    credential_id = UUID(response.json()["credential_id"])
    assert "token" not in response.json()
    assert exchange(auth, pairing).status_code == 404
    headers = {"Authorization": "Bearer " + pairing.machine_secret}
    registration = Registration(**profile("LA-01").model_dump(), session_id=uuid4())
    route = "/api/v1/workers/register"
    registered = auth.client.post(route, json=registration.model_dump(mode="json"), headers=headers)
    assert registered.status_code == 200, registered.text
    node_id = registered.json()["node_id"]
    assert UUID(node_id) == credential_id
    heartbeat = Heartbeat(session_id=registration.session_id, resources=registration.resources)
    assert (
        auth.client.post(
            f"/api/v1/workers/{node_id}/heartbeat",
            json=heartbeat.model_dump(mode="json"),
            headers=headers,
        ).status_code
        == 200
    )
    reconnect = registration.model_copy(update={"session_id": uuid4()})
    assert (
        auth.client.post(route, json=reconnect.model_dump(mode="json"), headers=headers).status_code
        == 409
    )
    with auth.database.sessions.begin() as session:
        node = session.get(Node, UUID(node_id))
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
    assert (
        auth.client.post(route, json=reconnect.model_dump(mode="json"), headers=headers).status_code
        == 200
    )
    assert (
        auth.post(
            auth.client, f"administration/node-credentials/{credential_id}/revoke"
        ).status_code
        == 200
    )
    assert (
        auth.client.post(route, json=reconnect.model_dump(mode="json"), headers=headers).status_code
        == 401
    )
    with auth.database.sessions() as session:
        credential = session.get(AccessCredential, credential_id)
        assert credential is not None
        assert credential.owner_id == UUID(response.json()["owner_id"])
        assert credential.token_hash != pairing.machine_secret
        audit = str([e.details for e in session.scalars(select(Event))])
        assert pairing.secret not in audit and pairing.machine_secret not in audit


@pytest.mark.parametrize("condition", ["expired", "disabled", "unlinked", "member", "revoked"])
def test_pairing_rechecks_owner_and_expiry(auth: AuthHarness, condition: str) -> None:
    pairing = Pairing()
    approve(auth, pairing)
    with auth.database.sessions.begin() as session:
        row = session.scalar(select(WorkerEnrollment))
        assert row is not None
        user = session.get(User, row.owner_id)
        assert user is not None
        if condition == "expired":
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif condition == "disabled":
            user.enabled = False
        elif condition == "unlinked":
            session.execute(delete(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        elif condition == "member":
            user.role, user.roles = "member", ["member"]
        else:
            row.consumed = True
    assert exchange(auth, pairing).status_code in (403, 404)
    with auth.database.sessions() as session:
        assert session.scalar(select(AccessCredential)) is None


def test_concurrent_exchange_issues_exactly_one_credential(auth: AuthHarness) -> None:
    pairing = Pairing()
    approve(auth, pairing)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: exchange(auth, pairing), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 404]
    with auth.database.sessions() as session:
        assert len(list(session.scalars(select(AccessCredential)))) == 1


def test_pairing_cannot_select_another_owner_or_skip_origin(auth: AuthHarness) -> None:
    pairing = Pairing()
    approve(auth, pairing)
    payload = {"challenge": Pairing().challenge, "name": "Mac", "owner_id": str(uuid4())}
    assert auth.post(auth.client, "administration/worker-enrollments", payload).status_code == 422
    assert (
        auth.client.post(
            "/api/v1/administration/worker-enrollments",
            json={
                "challenge": Pairing().challenge,
                "name": "Mac",
            },
        ).status_code
        == 403
    )


def test_owner_can_cancel_unused_pairing(auth: AuthHarness) -> None:
    pairing = Pairing()
    approve(auth, pairing)
    assert (
        auth.post(
            auth.client,
            "administration/worker-enrollments/revoke",
            {
                "challenge": pairing.challenge,
                "name": "Remote Mac",
            },
        ).status_code
        == 200
    )
    assert exchange(auth, pairing).status_code == 404


def test_other_admin_cannot_revoke_owner_pairing(auth: AuthHarness) -> None:
    pairing = Pairing()
    approve(auth, pairing)
    invite = auth.invite("other@example.invalid", ["platform_admin"])
    other = auth.browser()
    assert auth.login(other, "other-sub", "other@example.invalid", invite).status_code == 303
    assert (
        auth.post(
            other,
            "administration/worker-enrollments/revoke",
            {
                "challenge": pairing.challenge,
                "name": "Remote Mac",
            },
        ).status_code
        == 404
    )
    assert exchange(auth, pairing).status_code == 200


def test_exchange_failure_rolls_back_without_consuming_grant(auth: AuthHarness) -> None:
    pairing = Pairing()
    approve(auth, pairing)
    # A pre-existing reserved name forces the existing uniqueness contract to fail.
    credential = auth.post(auth.client, "administration/node-credentials", {"name": "Remote Mac"})
    assert credential.status_code == 201
    assert exchange(auth, pairing).status_code == 409
    with auth.database.sessions() as session:
        row = session.scalar(select(WorkerEnrollment))
        assert row is not None and not row.consumed
        assert len(list(session.scalars(select(AccessCredential)))) == 1


def connected_computer(auth: AuthHarness) -> tuple[Pairing, str, Registration]:
    pairing = Pairing()
    approve(auth, pairing)
    identity = exchange(auth, pairing).json()
    registration = Registration(**profile("LA-01").model_dump(), session_id=uuid4())
    registered = auth.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers={"Authorization": "Bearer " + pairing.machine_secret},
    )
    assert registered.status_code == 200, registered.text
    return pairing, identity["credential_id"], registration


def reconnect_approval(auth: AuthHarness, pairing: Pairing, reconnect: bool = True) -> Any:
    return auth.post(
        auth.client,
        "administration/worker-enrollments",
        {
            "challenge": pairing.challenge,
            "name": "Remote Mac",
            "reconnect": reconnect,
        },
    )


@pytest.mark.parametrize("revoked", [False, True])
def test_reconnect_keeps_one_node_and_permanently_retires_old_credential(
    auth: AuthHarness,
    revoked: bool,
) -> None:
    original, old_id, registration = connected_computer(auth)
    with auth.database.sessions.begin() as session:
        node = session.get(Node, UUID(old_id))
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
    if revoked:
        assert (
            auth.post(auth.client, f"administration/node-credentials/{old_id}/revoke").status_code
            == 200
        )
    replacement = Pairing()
    assert reconnect_approval(auth, replacement, False).status_code == 409
    assert reconnect_approval(auth, replacement).status_code == 201
    response = exchange(auth, replacement)
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Remote Mac"
    assert response.json()["credential_id"] != old_id
    assert exchange(auth, replacement).status_code == 404
    registration = registration.model_copy(update={"session_id": uuid4()})
    route = "/api/v1/workers/register"
    assert (
        auth.client.post(
            route,
            json=registration.model_dump(mode="json"),
            headers={
                "Authorization": "Bearer " + original.machine_secret,
            },
        ).status_code
        == 401
    )
    response = auth.client.post(
        route,
        json=registration.model_dump(mode="json"),
        headers={
            "Authorization": "Bearer " + replacement.machine_secret,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["node_id"] == old_id
    with auth.database.sessions() as session:
        nodes = list(session.scalars(select(Node)))
        assert len(nodes) == 1 and nodes[0].name == "Remote Mac"
        old = session.get(AccessCredential, UUID(old_id))
        assert old is not None and old.revoked and old.node_id is None
        active = list(
            session.scalars(select(AccessCredential).where(AccessCredential.revoked.is_(False)))
        )
        assert len(active) == 1 and str(active[0].node_id) == old_id
        details = str([e.details for e in session.scalars(select(Event))])
        assert original.machine_secret not in details and replacement.machine_secret not in details


def test_reconnect_rechecks_liveness_and_owner_approval(auth: AuthHarness) -> None:
    original, old_id, registration = connected_computer(auth)
    replacement = Pairing()
    assert reconnect_approval(auth, replacement).status_code == 409
    with auth.database.sessions.begin() as session:
        node = session.get(Node, UUID(old_id))
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
    assert reconnect_approval(auth, replacement).status_code == 201
    # A late old-worker heartbeat between approval and exchange blocks replacement.
    heartbeat = Heartbeat(session_id=registration.session_id, resources=registration.resources)
    assert (
        auth.client.post(
            f"/api/v1/workers/{old_id}/heartbeat",
            json=heartbeat.model_dump(mode="json"),
            headers={"Authorization": "Bearer " + original.machine_secret},
        ).status_code
        == 200
    )
    assert exchange(auth, replacement).status_code == 409
    with auth.database.sessions() as session:
        old = session.get(AccessCredential, UUID(old_id))
        assert old is not None and not old.revoked and str(old.node_id) == old_id


def test_other_admin_cannot_replace_owned_computer(auth: AuthHarness) -> None:
    _, _, _ = connected_computer(auth)
    invitation = auth.invite("other@example.invalid", ["platform_admin"])
    other = auth.browser()
    assert auth.login(other, "other-sub", "other@example.invalid", invitation).status_code == 303
    assert (
        auth.post(
            other,
            "administration/worker-enrollments",
            {
                "challenge": Pairing().challenge,
                "name": "Remote Mac",
                "reconnect": True,
            },
        ).status_code
        == 404
    )


def test_two_approved_reconnections_replace_only_the_bound_old_credential(
    auth: AuthHarness,
) -> None:
    _, old_id, _ = connected_computer(auth)
    with auth.database.sessions.begin() as session:
        node = session.get(Node, UUID(old_id))
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
    pairings = [Pairing(), Pairing()]
    for pairing in pairings:
        assert reconnect_approval(auth, pairing).status_code == 201
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda p: exchange(auth, p), pairings))
    assert sorted(r.status_code for r in responses) == [200, 409]
    with auth.database.sessions() as session:
        assert len(list(session.scalars(select(Node)))) == 1
        assert len(list(session.scalars(select(AccessCredential)))) == 2


@pytest.mark.parametrize("blocked", ["disabled", "draining", "unfinished"])
def test_reconnect_preserves_disabled_controls_and_unfinished_attempts(
    auth: AuthHarness,
    blocked: str,
) -> None:
    _, old_id, _ = connected_computer(auth)
    with auth.database.sessions.begin() as session:
        node = session.get(Node, UUID(old_id))
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
        if blocked != "unfinished":
            node.state = blocked
        else:
            workspace = Workspace(owner_id=node.owner_id, name="Existing work")
            session.add(workspace)
            session.flush()
            job = Job(
                owner_id=node.owner_id,
                workspace_id=workspace.id,
                type="synthetic",
                status="RUNNING",
                assigned_node_id=node.id,
            )
            session.add(job)
            session.flush()
            session.add(
                Attempt(
                    job_id=job.id,
                    node_id=node.id,
                    number=1,
                    fencing_token=1,
                    status="RUNNING",
                    lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
                )
            )
    assert reconnect_approval(auth, Pairing()).status_code == 409
    with auth.database.sessions() as session:
        old = session.get(AccessCredential, UUID(old_id))
        assert old is not None and not old.revoked
