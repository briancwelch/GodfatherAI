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
    Event,
    GoogleIdentity,
    Node,
    User,
    WorkerEnrollment,
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
