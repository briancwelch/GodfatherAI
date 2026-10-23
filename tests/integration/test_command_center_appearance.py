"""Real persistence, ownership and authorization for Command Center customization."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.models import AccessCredential, Event, HumanSession, Node, User
from godfather_api.nodes import token_digest
from godfather_api.provision import provision
from sqlalchemy import select

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h

pytestmark = pytest.mark.integration


def test_appearance_persists_and_requires_platform_permission(h: Harness) -> None:
    endpoint = "/api/v1/appearance"
    assert h.client.get(endpoint).status_code == 401
    assert h.client.get(endpoint, headers=headers(h.workers[0])).status_code == 401
    original = h.client.get(endpoint, headers=headers(h.admin)).json()
    updated = {
        **original,
        "font": "verdana",
        "font_size": 15,
        "striped_tables": True,
        "navigation_width": 240,
        "button_variant": "outline",
        "control_size": "large",
        "panel_padding": 24,
        "panel_shadow": "medium",
        "table_borders": True,
        "table_hover": False,
        "toast_position": "top-start",
        "toast_width": 420,
        "progress_height": 18,
        "progress_striped": False,
        "progress_animated": False,
        "warning_color": "#f9bc00",
    }
    assert h.client.post(endpoint, json=updated, headers=headers(h.admin)).json() == updated
    # Read via a new API process lifespan; PostgreSQL, not process/browser state, is authoritative.
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        assert restarted.get(endpoint, headers=headers(h.admin)).json() == updated
    invalid = {**updated, "font": "url(https://untrusted.invalid/font)"}
    assert h.client.post(endpoint, json=invalid, headers=headers(h.admin)).status_code == 422
    invalid = {**updated, "light": {**updated["light"], "foreground": "#ffffff"}}
    assert h.client.post(endpoint, json=invalid, headers=headers(h.admin)).status_code == 422
    # Use the actual human session path to exercise a member and origin enforcement.
    with h.database.sessions.begin() as session:
        actor = session.get(User, UUID(h.admin["owner_id"]))
        assert actor is not None
        actor.role = "member"
        actor.roles = ["member"]
        session.add(
            HumanSession(
                owner_id=actor.id,
                token_hash=token_digest("s" * 43),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    member_headers = {"X-Godfather-Session": "s" * 43, "Origin": "http://127.0.0.1:3000"}
    assert h.client.get(endpoint, headers=member_headers).json() == updated
    assert h.client.post(endpoint, json=updated, headers=member_headers).status_code == 403
    assert (
        h.client.post(endpoint, json=updated, headers={"X-Godfather-Session": "s" * 43}).status_code
        == 403
    )


def test_credential_bulk_delete_is_atomic_owner_scoped_revokes_and_retains_history(
    h: Harness,
) -> None:
    endpoint = "/api/v1/administration/bulk-delete"
    ids = [w["credential_id"] for w in h.workers]
    outsider = provision(h.database, "admin", email="credential-outsider@example.invalid")
    payload = {"kind": "node-credentials", "ids": ids}
    assert h.client.post(endpoint, json=payload, headers=headers(outsider)).status_code == 404
    assert h.client.post(endpoint, json=payload, headers=headers(h.workers[0])).status_code == 401
    assert (
        h.client.post(
            endpoint, json={**payload, "ids": [ids[0], str(uuid4())]}, headers=headers(h.admin)
        ).status_code
        == 404
    )
    with h.database.sessions() as session:
        assert all(
            not c.revoked
            for c in session.scalars(
                select(AccessCredential).where(AccessCredential.id.in_([UUID(i) for i in ids]))
            )
        )
    for _ in range(2):
        assert h.client.post(endpoint, json=payload, headers=headers(h.admin)).status_code == 200
    listing = h.client.get(
        "/api/v1/administration/node-credentials?paged=true", headers=headers(h.admin)
    ).json()
    assert listing["total"] == 0 and listing["items"] == []
    for worker, registration in zip(h.workers, h.registrations, strict=True):
        assert (
            h.client.post(
                "/api/v1/workers/register",
                json=registration.model_dump(mode="json"),
                headers=headers(worker),
            ).status_code
            == 401
        )
    with h.database.sessions() as session:
        for ident in ids:
            credential = session.get(AccessCredential, UUID(ident))
            node = session.get(Node, UUID(ident))
            assert credential is not None and credential.revoked and credential.deleted_at
            assert node is not None and node.state == "disabled"
        events = list(
            session.scalars(select(Event).where(Event.type == "security.node_credential_deleted"))
        )
        assert len(events) == 2
    # New pairing may reuse the original name; deleted tokens never work again.
    assert (
        h.client.post(
            "/api/v1/administration/node-credentials",
            json={"name": "LV-01"},
            headers=headers(h.admin),
        ).status_code
        == 201
    )


def test_node_owner_name_and_worker_build_are_durable_and_legacy_is_unknown(h: Harness) -> None:
    worker = h.workers[0]
    registration = h.registrations[0].model_copy(update={"worker_version": "0.4.1-rc.4"})
    assert (
        h.client.post(
            "/api/v1/workers/register",
            json=registration.model_dump(mode="json"),
            headers=headers(worker),
        ).status_code
        == 200
    )
    app = h.client.app
    assert isinstance(app, FastAPI)
    with h.database.sessions.begin() as session:
        owner = session.get(User, UUID(h.admin["owner_id"]))
        assert owner is not None
        owner.display_name = "Owner display name"
    response = h.client.get("/api/v1/command-center?section=nodes", headers=headers(h.admin))
    by_id = {n["node_id"]: n for n in response.json()["nodes"]}
    node = by_id[worker["credential_id"]]
    assert node["owner_name"] == "Owner display name"
    assert node["worker_version"] == "0.4.1-rc.4"
    assert by_id[h.workers[1]["credential_id"]].get("worker_version") is None
    detail = h.client.get(
        f"/api/v1/command-center/nodes/{worker['credential_id']}", headers=headers(h.admin)
    ).json()
    assert detail["node"]["owner_name"] == "Owner display name"
    assert detail["node"]["worker_version"] == "0.4.1-rc.4"


def test_audit_and_activity_resolve_names_without_exposing_an_account_directory(h: Harness) -> None:
    with h.database.sessions.begin() as session:
        owner = session.get(User, UUID(h.admin["owner_id"]))
        assert owner is not None
        owner.display_name = "Readable actor"
    response = h.client.get("/api/v1/administration/audit?paged=true", headers=headers(h.admin))
    assert response.status_code == 200
    rows = response.json()["items"]
    assert rows and any(e["actor_name"] == "Readable actor" for e in rows)
    assert all(
        e["actor_name"] == "Readable actor" for e in rows if e["actor_id"] == h.admin["owner_id"]
    )
    events = h.client.get("/api/v1/command-center/events", headers=headers(h.admin)).json()["items"]
    assert any(e["actor_name"] == "Readable actor" for e in events)
