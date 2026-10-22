"""Self-service profile boundaries and global authorized-workspace summaries."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from godfather_api.models import HumanSession, Job, User, Workspace
from godfather_api.nodes import token_digest
from godfather_api.provision import provision

from tests.integration.test_authentication import AuthHarness
from tests.integration.test_authentication import auth as auth
from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_nodes import database as database

pytestmark = pytest.mark.integration


def test_custom_profile_survives_another_google_sign_in(auth: AuthHarness) -> None:
    assert auth.login(auth.client).status_code == 303
    payload = {"display_name": "Chosen name", "picture": None, "location": "Optional city"}
    assert auth.post(auth.client, "account/profile", payload).status_code == 200
    assert auth.post(auth.client, "auth/logout").status_code == 200
    assert auth.login(auth.client).status_code == 303
    user = auth.client.get("/api/v1/auth/me").json()
    assert (
        user["display_name"] == "Chosen name"
        and user["picture"] is None
        and user["location"] == "Optional city"
    )


def test_profile_writes_only_the_signed_in_account(h: Harness) -> None:
    payload = {
        "display_name": "Updated owner",
        "picture": "https://example.invalid/avatar.png",
        "location": "Shared city",
    }
    path = "/api/v1/account/profile"
    with h.database.sessions.begin() as session:
        actor = session.get(User, UUID(h.admin["owner_id"]))
        assert actor is not None
        actor.role, actor.roles = "member", ["member"]
        session.add(
            HumanSession(
                owner_id=actor.id,
                token_hash=token_digest("p" * 43),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    own_headers = {"X-Godfather-Session": "p" * 43, "Origin": "http://127.0.0.1:3000"}
    response = h.client.post(path, json=payload, headers=own_headers)
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Updated owner"
    assert response.json()["location"] == "Shared city"
    with h.database.sessions() as session:
        user = session.get(User, UUID(h.admin["owner_id"]))
        assert user is not None and user.profile["customized"] is True
    assert h.client.post(path, json=payload, headers=headers(h.workers[0])).status_code == 401
    assert (
        h.client.post(
            path, json={**payload, "picture": "javascript:alert(1)"}, headers=own_headers
        ).status_code
        == 422
    )
    assert (
        h.client.post(
            path, json={**payload, "display_name": "   "}, headers=own_headers
        ).status_code
        == 422
    )
    assert (
        h.client.post(
            path, json={**payload, "user_id": h.workers[0]["owner_id"]}, headers=own_headers
        ).status_code
        == 422
    )


def test_global_overview_aggregates_visible_workspaces_only(h: Harness) -> None:
    outsider = provision(h.database, "admin", email="private-overview@example.invalid")
    with h.database.sessions.begin() as session:
        visible = Workspace(name="Another owned workspace", owner_id=UUID(h.admin["owner_id"]))
        hidden = Workspace(name="Hidden workspace", owner_id=UUID(outsider["owner_id"]))
        session.add_all([visible, hidden])
        session.flush()
        visible_id, hidden_id = visible.id, hidden.id
        for workspace in (visible, hidden):
            session.add(
                Job(
                    owner_id=workspace.owner_id,
                    workspace_id=workspace.id,
                    type="synthetic.echo",
                    input_refs={"value": "fixture"},
                )
            )
    data = h.client.get("/api/v1/command-center", headers=headers(h.admin)).json()
    assert data["workspace_id"] is None
    assert data["job_counts"] == {"PENDING": 1}
    assert {job["workspace_id"] for job in data["jobs"]} == {str(visible_id)}
    assert str(hidden_id) not in {w["id"] for w in data["workspaces"]}
    selected = h.client.get(
        f"/api/v1/command-center?workspace_id={h.workspace_id}", headers=headers(h.admin)
    ).json()
    assert selected["workspace_id"] == str(h.workspace_id) and selected["jobs"] == []
