"""Actual PostgreSQL/FastAPI authentication; only Google's network is mocked."""

from collections.abc import Iterator
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from godfather_api import authentication
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.models import (
    AccessCredential,
    Event,
    GoogleIdentity,
    HumanSession,
    Invitation,
    Job,
    LoginTransaction,
    Node,
    User,
    Workspace,
)
from godfather_api.nodes import token_digest
from sqlalchemy import select

from tests.integration.test_nodes import database as database
from tests.integration.test_nodes import registration
from tests.oidc_provider import OIDCProvider
from tests.test_agent_runtime import model

pytestmark = pytest.mark.integration
ORIGIN = {"Origin": "http://127.0.0.1:3000"}


class AuthHarness:
    def __init__(self, database: Database, stack: ExitStack) -> None:
        self.database, self.stack = database, stack
        self.provider = OIDCProvider()
        self.settings = Settings(
            health_monitor_enabled=False,
            test_legacy_credentials=False,
            google_client_id="test-google-client",
            google_client_secret="test-secret",
            google_bootstrap_subject="first-sub",
            google_bootstrap_email="first@example.invalid",
        )
        self.client = self.browser()
        self.last_state = ""
        self.last_browser = ""

    def browser(self) -> TestClient:
        return self.stack.enter_context(TestClient(create_app(self.settings)))

    def login(
        self,
        client: TestClient,
        subject: str = "first-sub",
        email: str = "first@example.invalid",
        invitation: str | None = None,
    ) -> Any:
        response = client.post(
            "/api/v1/auth/start",
            json={"invitation": invitation},
            headers=ORIGIN,
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["scope"] == ["openid email profile"]
        assert query["response_type"] == ["code"] and query["code_challenge_method"] == ["S256"]
        self.provider.challenge = query["code_challenge"][0]
        code = subject + str(len(self.provider.codes))
        self.last_state = query["state"][0]
        self.last_browser = str(client.cookies.get("godfather_login"))
        self.provider.codes[code] = {
            "sub": subject,
            "email": email,
            "email_verified": True,
            "name": "Verified " + subject,
            "nonce": query["nonce"][0],
        }
        return client.get(
            "/api/v1/auth/callback",
            params={"state": query["state"][0], "code": code},
            follow_redirects=False,
        )

    def post(self, client: TestClient, path: str, body: object | None = None) -> Any:
        return client.post("/api/v1/" + path, json=body or {}, headers=ORIGIN)

    def invite(self, email: str, roles: list[str]) -> str:
        response = self.post(
            self.client, "administration/invitations", {"email": email, "roles": roles}
        )
        assert response.status_code == 201, response.text
        return str(response.json()["invitation_token"])


@pytest.fixture
def auth(database: Database, monkeypatch: pytest.MonkeyPatch) -> Iterator[AuthHarness]:
    with ExitStack() as stack:
        harness = AuthHarness(database, stack)
        monkeypatch.setattr(authentication, "google_client", harness.provider.client)
        yield harness


def test_google_bootstrap_opaque_cookie_logout_and_audit(auth: AuthHarness) -> None:
    response = auth.login(auth.client)
    assert response.headers["location"] == auth.settings.web_origin + "/"
    cookie = response.headers.get_list("set-cookie")[-1]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age=28800" in cookie
    account = auth.client.get("/api/v1/auth/me").json()
    assert (
        account["roles"] == ["platform_admin"] and account["display_name"] == "Verified first-sub"
    )
    assert auth.provider.verifier_checked
    with auth.database.sessions() as session:
        identity = session.scalar(select(GoogleIdentity))
        assert identity is not None and identity.subject == "first-sub"
        row = session.scalar(select(HumanSession))
        assert row is not None and row.token_hash != auth.client.cookies.get("godfather_session")
        text = str([e.details for e in session.scalars(select(Event))])
        assert "test-provider-token" not in text and "test-secret" not in text
    assert auth.post(auth.client, "auth/logout").status_code == 200
    assert auth.client.get("/api/v1/auth/me").status_code == 401
    with auth.database.sessions() as session:
        assert "security.logout" in session.scalars(select(Event.type)).all()


@pytest.mark.parametrize(
    "mode", ["nonce", "issuer", "audience", "expired", "unverified", "signature"]
)
def test_oidc_invalid_tokens_are_rejected_by_library(auth: AuthHarness, mode: str) -> None:
    auth.provider.mode = mode
    assert auth.login(auth.client).headers["location"].endswith("?auth=denied")
    assert auth.client.get("/api/v1/auth/me").status_code == 401
    with auth.database.sessions() as session:
        assert session.scalar(select(User)) is None
        assert "security.login_failed" in session.scalars(select(Event.type)).all()


def test_invitation_only_equal_admins_contributor_roles_and_private_workspaces(
    auth: AuthHarness,
) -> None:
    auth.login(auth.client)
    second, contributor, outsider = auth.browser(), auth.browser(), auth.browser()
    auth.login(
        second,
        "second-sub",
        "second@example.invalid",
        auth.invite("second@example.invalid", ["platform_admin"]),
    )
    auth.login(
        contributor,
        "contributor-sub",
        "contributor@example.invalid",
        auth.invite("contributor@example.invalid", ["contributor", "member"]),
    )
    assert (
        auth.login(outsider, "outsider-sub", "outsider@example.invalid")
        .headers["location"]
        .endswith("?auth=denied")
    )
    assert outsider.get("/api/v1/command-center").status_code == 401
    for client in (auth.client, second):
        assert client.get("/api/v1/administration/users").status_code == 200
    assert contributor.get("/api/v1/administration/users").status_code == 403
    assert (
        auth.post(
            contributor,
            "administration/invitations",
            {"email": "new@example.invalid", "roles": ["platform_admin"]},
        ).status_code
        == 403
    )
    workspace = auth.post(auth.client, "administration/workspaces", {"name": "Private"}).json()[
        "id"
    ]
    assert second.get(f"/api/v1/command-center?workspace_id={workspace}").status_code == 404
    assert (
        auth.post(
            second,
            f"administration/workspaces/{workspace}/members",
            {"user_id": second.get("/api/v1/auth/me").json()["id"], "role": "admin"},
        ).status_code
        == 404
    )
    second_id = second.get("/api/v1/auth/me").json()["id"]
    assert (
        auth.post(
            auth.client,
            f"administration/workspaces/{workspace}/members",
            {"user_id": second_id, "role": "admin"},
        ).status_code
        == 200
    )
    assert second.get(f"/api/v1/command-center?workspace_id={workspace}").status_code == 200
    assert (
        contributor.get(f"/api/v1/administration/workspaces/{workspace}/members").status_code == 404
    )
    contributor_id = contributor.get("/api/v1/auth/me").json()["id"]
    assert (
        auth.post(
            auth.client,
            f"administration/users/{contributor_id}",
            {"roles": ["member"], "enabled": False},
        ).status_code
        == 200
    )
    assert contributor.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("mode", ["expired", "revoked", "used", "wrong_email"])
def test_invitations_expiration_revocation_reuse_and_email_binding(
    auth: AuthHarness, mode: str
) -> None:
    auth.login(auth.client)
    token = auth.invite("invited@example.invalid", ["member"])
    with auth.database.sessions.begin() as session:
        invite = session.scalar(
            select(Invitation).where(Invitation.token_hash == token_digest(token))
        )
        assert invite is not None
        if mode == "expired":
            invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        if mode == "revoked":
            invite.revoked = True
        if mode == "used":
            invite.used_by = session.scalar(select(User.id))
    browser = auth.browser()
    response = (
        auth.login(
            browser,
            "new-sub",
            "wrong@example.invalid" if mode == "wrong_email" else "invited@example.invalid",
            token,
        )
        if mode == "wrong_email"
        else browser.post(
            "/api/v1/auth/start", json={"invitation": token}, headers=ORIGIN, follow_redirects=False
        )
    )
    assert response.headers["location"].endswith("?auth=denied")
    assert browser.get("/api/v1/auth/me").status_code == 401


def test_state_browser_binding_expiration_and_replay(auth: AuthHarness) -> None:
    start = auth.client.post("/api/v1/auth/start", json={}, headers=ORIGIN, follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    assert (
        auth.browser()
        .get(f"/api/v1/auth/callback?state={state}&code=unused", follow_redirects=False)
        .headers["location"]
        .endswith("?auth=denied")
    )
    with auth.database.sessions.begin() as session:
        row = session.scalar(select(LoginTransaction))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (
        auth.client.get(f"/api/v1/auth/callback?state={state}&code=unused", follow_redirects=False)
        .headers["location"]
        .endswith("?auth=denied")
    )
    auth.login(auth.client)
    with auth.database.sessions() as session:
        assert len(session.scalars(select(HumanSession)).all()) == 1
        transaction = session.scalar(
            select(LoginTransaction).where(LoginTransaction.consumed.is_(True))
        )
        assert transaction is not None and transaction.verifier == ""
    # Callback after a successful flow has no browser binding cookie.
    assert (
        auth.client.get(f"/api/v1/auth/callback?state={state}&code=unused", follow_redirects=False)
        .headers["location"]
        .endswith("?auth=denied")
    )


@pytest.mark.parametrize("mode", ["expired", "revoked", "disabled"])
def test_sessions_expire_revoke_and_account_disabling(auth: AuthHarness, mode: str) -> None:
    auth.login(auth.client)
    with auth.database.sessions.begin() as session:
        row = session.scalar(select(HumanSession))
        user = session.scalar(select(User))
        assert row is not None and user is not None
        if mode == "expired":
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        if mode == "revoked":
            row.revoked = True
        if mode == "disabled":
            user.enabled = False
    assert auth.client.get("/api/v1/command-center").status_code == 401


def test_node_owner_bound_credentials_impersonation_and_revocation(auth: AuthHarness) -> None:
    auth.login(auth.client)
    second = auth.browser()
    auth.login(
        second,
        "second-sub",
        "second@example.invalid",
        auth.invite("second@example.invalid", ["platform_admin"]),
    )
    credential = auth.post(
        auth.client, "administration/node-credentials", {"name": "Owned local worker"}
    ).json()
    worker_headers = {"Authorization": "Bearer " + credential["token"]}
    payload = registration()
    assert (
        auth.client.post(
            "/api/v1/workers/register", json=payload, headers=worker_headers
        ).status_code
        == 200
    )
    node = credential["node_id"]
    assert auth.post(second, f"nodes/{node}/control", {"action": "enable"}).status_code == 403
    assert auth.post(second, f"nodes/{node}/control", {"action": "revoke"}).status_code == 403
    assert (
        auth.client.post(
            "/api/v1/workers/register",
            json={**payload, "owner_id": second.get("/api/v1/auth/me").json()["id"]},
            headers=worker_headers,
        ).status_code
        == 422
    )
    assert (
        auth.client.post(
            f"/api/v1/workers/{UUID(int=1)}/heartbeat",
            json={"session_id": payload["session_id"], "resources": payload["resources"]},
            headers=worker_headers,
        ).status_code
        == 403
    )
    assert auth.post(auth.client, f"nodes/{node}/control", {"action": "revoke"}).status_code == 200
    assert (
        auth.client.post(
            "/api/v1/workers/register", json=payload, headers=worker_headers
        ).status_code
        == 401
    )
    assert (
        auth.client.get("/api/v1/command-center", headers=worker_headers).status_code == 200
    )  # human cookie remains independent
    assert auth.browser().get("/api/v1/command-center", headers=worker_headers).status_code == 401
    pending = auth.post(
        auth.client, "administration/node-credentials", {"name": "Not yet registered"}
    ).json()
    assert (
        auth.post(
            second, f"administration/node-credentials/{pending['node_id']}/revoke"
        ).status_code
        == 404
    )
    assert (
        auth.post(
            auth.client, f"administration/node-credentials/{pending['node_id']}/revoke"
        ).status_code
        == 200
    )
    assert (
        auth.client.post(
            "/api/v1/workers/register",
            json=payload,
            headers={"Authorization": "Bearer " + pending["token"]},
        ).status_code
        == 401
    )


def test_csrf_rate_limiting_and_no_legacy_human_login(auth: AuthHarness) -> None:
    assert auth.client.post("/api/v1/auth/start", json={}).status_code == 403
    assert (
        auth.client.post(
            "/api/v1/auth/start", json={}, headers={"Origin": "https://attacker.invalid"}
        ).status_code
        == 403
    )
    auth.login(auth.client)
    assert auth.client.post("/api/v1/auth/logout").status_code == 403
    assert auth.client.get("/api/v1/command-center").status_code == 200
    for _ in range(auth.settings.authentication_limit - 1):
        assert (
            auth.client.post(
                "/api/v1/auth/start", json={}, headers=ORIGIN, follow_redirects=False
            ).status_code
            == 303
        )
    assert auth.client.post("/api/v1/auth/start", json={}, headers=ORIGIN).status_code == 429
    assert (
        auth.browser()
        .get("/api/v1/command-center", headers={"Authorization": "Bearer " + "a" * 43})
        .status_code
        == 401
    )


def test_subject_is_stable_and_email_does_not_link_legacy_users(auth: AuthHarness) -> None:
    auth.login(auth.client)
    first_id = auth.client.get("/api/v1/auth/me").json()["id"]
    auth.login(auth.client, email="renamed@example.invalid")
    assert auth.client.get("/api/v1/auth/me").json()["id"] == first_id
    with auth.database.sessions.begin() as session:
        session.add(
            User(email="legacy@example.invalid", display_name="Legacy", role="platform_admin")
        )
    other = auth.browser()
    assert (
        auth.login(
            other,
            "new-sub",
            "legacy@example.invalid",
            auth.invite("legacy@example.invalid", ["member"]),
        )
        .headers["location"]
        .endswith("?auth=denied")
    )


def test_last_admin_protection_and_session_revocation_api(auth: AuthHarness) -> None:
    auth.login(auth.client)
    user_id = auth.client.get("/api/v1/auth/me").json()["id"]
    assert (
        auth.post(
            auth.client, f"administration/users/{user_id}", {"roles": ["member"], "enabled": True}
        ).status_code
        == 409
    )
    another = auth.browser()
    auth.login(another)
    assert auth.post(auth.client, "auth/sessions/revoke").status_code == 200
    assert another.get("/api/v1/auth/me").status_code == 401
    assert auth.client.get("/api/v1/auth/me").status_code == 401


def test_consumed_state_cannot_be_replayed_even_with_copied_browser_cookie(
    auth: AuthHarness,
) -> None:
    auth.login(auth.client)
    auth.client.cookies.set("godfather_login", auth.last_browser)
    response = auth.client.get(
        "/api/v1/auth/callback",
        params={"state": auth.last_state, "code": "replay"},
        follow_redirects=False,
    )
    assert response.headers["location"].endswith("?auth=denied")
    with auth.database.sessions() as session:
        assert len(session.scalars(select(HumanSession)).all()) == 1


def test_workspace_model_tool_policy_is_enforced_and_can_be_revoked(auth: AuthHarness) -> None:
    from godfather_api.scheduler import permitted

    auth.login(auth.client)
    user = auth.client.get("/api/v1/auth/me").json()
    workspace = auth.post(auth.client, "administration/workspaces", {"name": "Policy test"}).json()[
        "id"
    ]
    credential = auth.post(
        auth.client, "administration/node-credentials", {"name": "Policy worker"}
    ).json()
    payload = registration()
    payload["inference_protocol_version"] = 1
    payload["model_deployments"] = [model().model_dump(mode="json")]
    assert (
        auth.client.post(
            "/api/v1/workers/register",
            json=payload,
            headers={"Authorization": "Bearer " + credential["token"]},
        ).status_code
        == 200
    )
    job = Job(
        owner_id=UUID(user["id"]),
        workspace_id=UUID(workspace),
        requirements={
            "model_selection": {"identifier": "fixture"},
            "tools": [{"name": "plan.describe", "version": 1}],
        },
    )

    def allowed() -> bool:
        with auth.database.sessions() as session:
            node = session.get(Node, UUID(credential["node_id"]))
            assert node is not None
            return permitted(session, job, node)

    assert not allowed()
    assert auth.client.get(f"/api/v1/models?workspace_id={workspace}").json() == []
    auth.post(
        auth.client,
        f"administration/workspaces/{workspace}/policy",
        {"allowed_models": ["fixture"], "allowed_tools": ["plan.describe@1"]},
    )
    assert allowed()
    assert len(auth.client.get(f"/api/v1/models?workspace_id={workspace}").json()) == 1
    auth.post(
        auth.client,
        f"administration/workspaces/{workspace}/policy",
        {"allowed_models": ["fixture"], "allowed_tools": []},
    )
    assert not allowed()


def test_cluster_health_and_audit_do_not_reveal_private_grant_ids(auth: AuthHarness) -> None:
    auth.login(auth.client)
    second = auth.browser()
    auth.login(
        second,
        "second-sub",
        "second@example.invalid",
        auth.invite("second@example.invalid", ["platform_admin"]),
    )
    workspace = auth.post(
        auth.client, "administration/workspaces", {"name": "Secret workspace"}
    ).json()["id"]
    credential = auth.post(
        auth.client, "administration/node-credentials", {"name": "Private grant worker"}
    ).json()
    payload = {**registration(), "allowed_workspace_ids": [workspace]}
    auth.client.post(
        "/api/v1/workers/register",
        json=payload,
        headers={"Authorization": "Bearer " + credential["token"]},
    )
    for path in (
        "nodes",
        f"nodes/{credential['node_id']}",
        "command-center",
        "command-center/events",
        "administration/audit",
    ):
        response = second.get("/api/v1/" + path)
        assert response.status_code == 200, response.text
        assert workspace not in response.text
    assert workspace in auth.client.get(f"/api/v1/nodes/{credential['node_id']}").text


def test_explicit_identity_migration_preserves_owned_resources(auth: AuthHarness) -> None:
    from godfather_api.identity import bind
    from godfather_api.provision import provision

    legacy = provision(auth.database, "admin", email="legacy-owner@example.invalid")
    user_id = UUID(legacy["owner_id"])
    with auth.database.sessions.begin() as session:
        workspace = Workspace(owner_id=user_id, name="Retained private workspace")
        session.add(workspace)
        session.flush()
        workspace_id = workspace.id
    bind(auth.database, "legacy-sub", user_id)
    auth.login(auth.client, "legacy-sub", "legacy-owner@example.invalid")
    assert auth.client.get("/api/v1/auth/me").json()["id"] == str(user_id)
    assert auth.client.get(f"/api/v1/command-center?workspace_id={workspace_id}").status_code == 200
    with auth.database.sessions() as session:
        credential = session.get(AccessCredential, UUID(legacy["credential_id"]))
        assert credential is not None and credential.revoked
