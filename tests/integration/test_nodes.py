"""Real PostgreSQL registration, credentials, process identity, and deterministic health."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.migrations import migration_config
from godfather_api.models import AccessCredential, Event, Node, User
from godfather_api.nodes import sweep_health
from godfather_api.provision import provision
from godfather_contracts import Registration
from godfather_worker.simulated import profile
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def database() -> Iterator[Database]:
    if os.getenv("GODFATHER_RUN_INTEGRATION") != "1":
        pytest.skip("requires disposable PostgreSQL godfather_test")
    settings = Settings(health_monitor_enabled=False)
    if settings.environment != "test" or settings.database_name != "godfather_test":
        pytest.fail("Only the explicitly disposable test database is permitted")
    command.upgrade(migration_config(), "head")
    command.downgrade(migration_config(), "base")
    command.upgrade(migration_config(), "head")
    database = Database(settings)
    yield database
    database.close()


@pytest.fixture
def admin(database: Database) -> dict[str, str]:
    return provision(database, "admin", email="phase03@example.invalid")


@pytest.fixture
def worker(database: Database, admin: dict[str, str]) -> dict[str, str]:
    return provision(database, "worker", owner_id=UUID(admin["owner_id"]), name="LV-01")


@pytest.fixture
def client(database: Database) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as client:
        yield client


def headers(credential: dict[str, str]) -> dict[str, str]:
    return {"Authorization": "Bearer " + credential["token"]}


def registration(name: str = "LV-01") -> dict[str, object]:
    return Registration(**profile(name).model_dump(), session_id=uuid4()).model_dump(mode="json")


def test_registration_records_owned_identity_and_normalized_capabilities(
    client: TestClient, database: Database, admin: dict[str, str], worker: dict[str, str]
) -> None:
    payload = registration()
    response = client.post("/api/v1/workers/register", json=payload, headers=headers(worker))
    assert response.status_code == 200, response.text
    node_id = response.json()["node_id"]
    assert node_id == worker["credential_id"]
    view = client.get(f"/api/v1/nodes/{node_id}", headers=headers(admin)).json()
    assert view["owner_id"] == admin["owner_id"]
    assert view["resources"]["source"] == "simulated"
    assert view["primary_capabilities"] == ["coding"]
    assert view["secondary_capabilities"] == ["research"]
    assert view["protocol_version"] == 1 and view["state"] == "online"
    assert view["last_heartbeat_at"].endswith("Z")
    assert worker["token"] not in str(view)
    assert len(client.get("/api/v1/nodes", headers=headers(admin)).json()) == 1
    with database.sessions() as session:
        credential = session.get(AccessCredential, UUID(worker["credential_id"]))
        assert credential is not None and credential.token_hash != worker["token"]
        events = list(session.scalars(select(Event.type).where(Event.node_id == UUID(node_id))))
        assert "node.registered" in events and "node.health_changed" in events


@pytest.mark.parametrize("token", [None, "Bearer bad", "Basic " + "a" * 43, "Bearer " + "a" * 43])
def test_registration_and_node_reads_require_valid_credentials(
    client: TestClient, token: str | None
) -> None:
    supplied = {"Authorization": token} if token else {}
    assert (
        client.post("/api/v1/workers/register", json=registration(), headers=supplied).status_code
        == 401
    )
    assert client.get("/api/v1/nodes", headers=supplied).status_code == 401


def test_scopes_duplicate_headers_and_protocol_validation(
    client: TestClient, admin: dict[str, str], worker: dict[str, str]
) -> None:
    payload = registration()
    assert (
        client.post("/api/v1/workers/register", json=payload, headers=headers(admin)).status_code
        == 401
    )
    assert client.get("/api/v1/nodes", headers=headers(worker)).status_code == 401
    duplicates = [("Authorization", "Bearer " + worker["token"])] * 2
    assert (
        client.post("/api/v1/workers/register", json=payload, headers=duplicates).status_code == 401
    )
    assert (
        client.post(
            "/api/v1/workers/register",
            json={**payload, "protocol_version": 2},
            headers=headers(worker),
        ).status_code
        == 426
    )
    assert (
        client.post(
            "/api/v1/workers/register",
            json={**payload, "owner_id": admin["owner_id"]},
            headers=headers(worker),
        ).status_code
        == 422
    )


def test_duplicate_names_and_live_processes_are_rejected(
    client: TestClient, database: Database, admin: dict[str, str], worker: dict[str, str]
) -> None:
    with pytest.raises(IntegrityError):
        provision(database, "worker", owner_id=UUID(admin["owner_id"]), name="LV-01")
    payload = registration()
    first = client.post("/api/v1/workers/register", json=payload, headers=headers(worker))
    assert first.status_code == 200
    assert (
        client.post("/api/v1/workers/register", json=payload, headers=headers(worker)).json()[
            "node_id"
        ]
        == first.json()["node_id"]
    )
    assert (
        client.post(
            "/api/v1/workers/register", json=registration(), headers=headers(worker)
        ).status_code
        == 409
    )


def test_concurrent_first_registration_creates_one_identity(
    client: TestClient, database: Database, worker: dict[str, str]
) -> None:
    def send(_: int) -> int:
        return client.post(
            "/api/v1/workers/register", json=registration(), headers=headers(worker)
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(send, range(2)))
    assert sorted(results) == [200, 409]
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Node)) == 1


def test_independent_expiration_reconnect_and_stale_process_fencing(
    client: TestClient, database: Database, admin: dict[str, str], worker: dict[str, str]
) -> None:
    other = provision(database, "worker", owner_id=UUID(admin["owner_id"]), name="LA-01")
    old = registration()
    node_id = client.post("/api/v1/workers/register", json=old, headers=headers(worker)).json()[
        "node_id"
    ]
    other_id = client.post(
        "/api/v1/workers/register", json=registration("LA-01"), headers=headers(other)
    ).json()["node_id"]
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        node = session.get(Node, UUID(node_id))
        assert node is not None
        node.last_heartbeat_at = now - timedelta(seconds=20)
    sweep_health(database, Settings(), now)
    assert (
        client.get(f"/api/v1/nodes/{node_id}", headers=headers(admin)).json()["state"] == "suspect"
    )
    sweep_health(database, Settings(), now + timedelta(seconds=10))
    nodes = {
        v["node_id"]: v["state"] for v in client.get("/api/v1/nodes", headers=headers(admin)).json()
    }
    assert nodes == {node_id: "offline", other_id: "online"}
    # Actual timestamps are moved past expiry before a replacement process takes over.
    with database.sessions.begin() as session:
        node = session.get(Node, UUID(node_id))
        assert node is not None
        node.last_heartbeat_at = now - timedelta(seconds=31)
    new = registration()
    assert (
        client.post("/api/v1/workers/register", json=new, headers=headers(worker)).json()["node_id"]
        == node_id
    )
    hb = {"session_id": old["session_id"], "resources": old["resources"]}
    assert (
        client.post(
            f"/api/v1/workers/{node_id}/heartbeat", json=hb, headers=headers(worker)
        ).status_code
        == 409
    )
    hb["session_id"] = new["session_id"]
    assert (
        client.post(
            f"/api/v1/workers/{node_id}/heartbeat", json=hb, headers=headers(worker)
        ).json()["state"]
        == "online"
    )
    assert (
        client.post(
            f"/api/v1/workers/{other_id}/heartbeat", json=hb, headers=headers(worker)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/workers/{node_id}/heartbeat",
            json={**hb, "protocol_version": 2},
            headers=headers(worker),
        ).status_code
        == 426
    )


def test_administrative_states_survive_heartbeat_expiry_and_revocation(
    client: TestClient, database: Database, admin: dict[str, str], worker: dict[str, str]
) -> None:
    payload = registration()
    node_id = client.post("/api/v1/workers/register", json=payload, headers=headers(worker)).json()[
        "node_id"
    ]
    route = f"/api/v1/nodes/{node_id}/control"
    hb = {"session_id": payload["session_id"], "resources": payload["resources"]}
    assert client.post(route, json={"action": "drain"}, headers=headers(worker)).status_code == 401
    assert (
        client.post(route, json={"action": "drain"}, headers=headers(admin)).json()["state"]
        == "draining"
    )
    assert (
        client.post(
            f"/api/v1/workers/{node_id}/heartbeat", json=hb, headers=headers(worker)
        ).json()["state"]
        == "draining"
    )
    sweep_health(database, Settings(), datetime.now(UTC) + timedelta(seconds=31))
    view = client.get(f"/api/v1/nodes/{node_id}", headers=headers(admin)).json()
    assert view["state"] == "draining" and view["connection_status"] == "offline"
    assert (
        client.post(route, json={"action": "disable"}, headers=headers(admin)).json()["state"]
        == "disabled"
    )
    assert (
        client.post(
            f"/api/v1/workers/{node_id}/heartbeat", json=hb, headers=headers(worker)
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/workers/register", json=payload, headers=headers(worker)).status_code
        == 403
    )
    assert client.post(route, json={"action": "enable"}, headers=headers(admin)).status_code == 200
    assert (
        client.post("/api/v1/workers/register", json=payload, headers=headers(worker)).status_code
        == 200
    )
    assert (
        client.post(route, json={"action": "revoke"}, headers=headers(admin)).json()["state"]
        == "disabled"
    )
    assert (
        client.post("/api/v1/workers/register", json=payload, headers=headers(worker)).status_code
        == 401
    )
    assert client.post(route, json={"action": "enable"}, headers=headers(admin)).status_code == 409


def test_disabled_owner_and_admin_role_enforced(
    client: TestClient, database: Database, admin: dict[str, str], worker: dict[str, str]
) -> None:
    with database.sessions.begin() as session:
        owner = session.get(User, UUID(admin["owner_id"]))
        assert owner is not None
        owner.enabled = False
    assert (
        client.post(
            "/api/v1/workers/register", json=registration(), headers=headers(worker)
        ).status_code
        == 403
    )
    assert client.get("/api/v1/nodes", headers=headers(admin)).status_code == 403
    with database.sessions.begin() as session:
        owner = session.get(User, UUID(admin["owner_id"]))
        assert owner is not None
        owner.enabled = True
        owner.role = "member"
    assert client.get("/api/v1/nodes", headers=headers(admin)).status_code == 403


def test_node_identity_telemetry_and_events_survive_application_restart(
    client: TestClient, database: Database, admin: dict[str, str], worker: dict[str, str]
) -> None:
    payload = registration()
    node_id = client.post("/api/v1/workers/register", json=payload, headers=headers(worker)).json()[
        "node_id"
    ]
    database.close()
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        response = restarted.get(f"/api/v1/nodes/{node_id}", headers=headers(admin))
        assert response.status_code == 200 and response.json()["resources"] == payload["resources"]
        assert (
            restarted.post(
                "/api/v1/workers/register", json=payload, headers=headers(worker)
            ).json()["node_id"]
            == node_id
        )
    with database.sessions() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Event).where(Event.node_id == UUID(node_id))
            )
            or 0
        ) >= 3


def test_two_equal_administrators_can_inspect_without_mutating_owner_policy(
    client: TestClient, database: Database, worker: dict[str, str]
) -> None:
    second = provision(database, "admin", email="second@example.invalid")
    node_id = client.post(
        "/api/v1/workers/register", json=registration(), headers=headers(worker)
    ).json()["node_id"]
    response = client.get(f"/api/v1/nodes/{node_id}", headers=headers(second))
    assert response.status_code == 200
    route = f"/api/v1/nodes/{node_id}/control"
    assert (
        client.post(
            route,
            json={"action": "enable", "contribution_policy": {"shell": True}},
            headers=headers(second),
        ).status_code
        == 422
    )
    with database.sessions() as session:
        node = session.get(Node, UUID(node_id))
        assert node is not None and node.contribution_policy == {}


def test_invalid_telemetry_and_validation_errors_do_not_echo_secrets(
    client: TestClient, worker: dict[str, str]
) -> None:
    payload = registration()
    node_id = client.post("/api/v1/workers/register", json=payload, headers=headers(worker)).json()[
        "node_id"
    ]
    resources = profile("LV-01").resources.model_dump(mode="json")
    resources["source"] = "physical"
    heartbeat = {"session_id": payload["session_id"], "resources": resources}
    assert (
        client.post(
            f"/api/v1/workers/{node_id}/heartbeat", json=heartbeat, headers=headers(worker)
        ).status_code
        == 422
    )
    response = client.post(
        "/api/v1/workers/register", json={"token": worker["token"]}, headers=headers(worker)
    )
    assert response.status_code == 422 and worker["token"] not in response.text


def test_failed_commit_returns_error_and_rolls_back_registration(
    client: TestClient, database: Database, worker: dict[str, str]
) -> None:
    def fail_commit(session: Session) -> None:
        raise OperationalError("private SQL", {}, Exception("private database detail"))

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = client.post(
            "/api/v1/workers/register", json=registration(), headers=headers(worker)
        )
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 500
    assert "private" not in response.text
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Node)) == 0
        assert (
            session.scalar(
                select(func.count()).select_from(Event).where(Event.type == "node.registered")
            )
            == 0
        )
