"""Real persistence/authorization; provider model-list HTTP is mocked, no billable calls."""

from uuid import UUID

import pytest
from godfather_api.account_providers import decrypt_key
from godfather_api.models import AccountProviderKey, ProviderConnection
from godfather_model_gateway import NativeModel
from pydantic import SecretStr
from sqlalchemy import select

from tests.integration.test_authentication import AuthHarness
from tests.integration.test_authentication import auth as auth
from tests.integration.test_nodes import database as database
from tests.integration.test_nodes import registration

pytestmark = pytest.mark.integration


def test_account_key_requires_both_computer_grant_and_worker_opt_in(
    auth: AuthHarness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    auth.settings.provider_vault_key = SecretStr("ab" * 32)
    assert auth.login(auth.client).status_code == 303
    first_id = auth.client.get("/api/v1/auth/me").json()["id"]
    own = auth.post(auth.client, "administration/workspaces", {"name": "Own workspace"}).json()
    second = auth.browser()
    assert (
        auth.login(
            second,
            "other",
            "other@example.invalid",
            auth.invite("other@example.invalid", ["platform_admin"]),
        ).status_code
        == 303
    )
    auth.post(second, "administration/workspaces", {"name": "Other private workspace"})
    first = auth.post(
        auth.client, "administration/node-credentials", {"name": "Allowed computer"}
    ).json()
    unselected = auth.post(
        auth.client, "administration/node-credentials", {"name": "Unselected computer"}
    ).json()
    foreign = auth.post(
        second, "administration/node-credentials", {"name": "Other computer"}
    ).json()
    clients = {}
    for credential in (first, unselected, foreign):
        worker = auth.browser()
        worker.headers["Authorization"] = "Bearer " + credential["token"]
        body = registration()
        assert worker.post("/api/v1/workers/register", json=body).status_code == 200
        clients[credential["node_id"]] = (worker, body)
    worker, body = clients[first["node_id"]]
    options = worker.post("/api/v1/workers/coding/options", json={})
    assert options.status_code == 200
    assert options.json()["owner_id"] == first_id
    assert [w["name"] for w in options.json()["workspaces"]] == ["Own workspace"]

    async def catalog(provider: str, key: str) -> list[NativeModel]:
        assert provider == "openai" and key == "fixture-private-api-key"
        return [
            NativeModel(
                identifier="gpt-4.1",
                context_window=8192,
                max_output_tokens=2048,
                structured_output=True,
            ),
            NativeModel(
                identifier="gpt-image-1.5", modality="image", context_window=1, max_output_tokens=1
            ),
        ]

    monkeypatch.setattr("godfather_api.account_providers.discover_catalog", catalog)
    route = "account/providers/openai"
    payload = {"api_key": "fixture-private-api-key", "allowed_node_ids": [first["node_id"]]}
    assert (
        auth.post(
            auth.client, route, {**payload, "allowed_node_ids": [foreign["node_id"]]}
        ).status_code
        == 404
    )
    assert auth.post(auth.client, route, payload).status_code == 200
    listing = auth.client.get("/api/v1/account/providers")
    assert "fixture-private-api-key" not in listing.text
    assert listing.json()["connections"][0]["connected"]
    assert second.get("/api/v1/account/providers").json()["connections"] == []
    path = f"/api/v1/workers/{first['node_id']}/account-providers"
    assert worker.post(path, json={"session_id": body["session_id"]}).status_code == 403
    body["runtimes"] = ["account-provider-keys-v1"]
    body["inference_protocol_version"] = 1
    assert worker.post("/api/v1/workers/register", json=body).status_code == 200
    response = worker.post(path, json={"session_id": body["session_id"]})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["providers"][0]["api_key"] == payload["api_key"]
    # Older/text-only workers must not receive the additive image model contract.
    assert len(response.json()["providers"][0]["model_catalog"]) == 1
    assert "modality" not in response.json()["providers"][0]["model_catalog"][0]
    body["runtimes"] = ["account-provider-keys-v1", "cloud-images-v1"]
    assert worker.post("/api/v1/workers/register", json=body).status_code == 200
    expanded = worker.post(path, json={"session_id": body["session_id"]}).json()
    assert len(expanded["providers"][0]["model_catalog"]) == 2
    other_worker, other_body = clients[unselected["node_id"]]
    other_body["runtimes"] = ["account-provider-keys-v1"]
    other_body["inference_protocol_version"] = 1
    assert other_worker.post("/api/v1/workers/register", json=other_body).status_code == 200
    assert (
        other_worker.post(
            f"/api/v1/workers/{unselected['node_id']}/account-providers",
            json={"session_id": other_body["session_id"]},
        ).json()["providers"]
        == []
    )
    assert other_worker.post(path, json={"session_id": body["session_id"]}).status_code in (
        401,
        403,
        404,
    )
    with auth.database.sessions() as session:
        row = session.scalar(select(AccountProviderKey))
        assert row is not None and "fixture-private-api-key" not in row.encrypted_key
        assert decrypt_key(row, auth.settings) == payload["api_key"]
        row.owner_id = UUID(foreign["owner_id"])
        with pytest.raises(Exception, match="503"):
            decrypt_key(row, auth.settings)
        connection = session.scalar(select(ProviderConnection))
        assert connection is not None and connection.policy["billing"] == "provider"
        assert connection.policy["rates"] == []
    assert "fixture-private-api-key" not in caplog.text
    assert (
        auth.post(
            second, route + "/computers", {"allowed_node_ids": [foreign["node_id"]]}
        ).status_code
        == 404
    )
    assert (
        auth.post(
            auth.client, route + "/computers", {"allowed_node_ids": [unselected["node_id"]]}
        ).status_code
        == 200
    )
    assert worker.post(path, json={"session_id": body["session_id"]}).json()["providers"] == []
    assert (
        auth.post(
            auth.client, route + "/computers", {"allowed_node_ids": [first["node_id"]]}
        ).status_code
        == 200
    )
    assert (
        worker.post(path, json={"session_id": body["session_id"]}).json()["providers"][0]["api_key"]
        == "fixture-private-api-key"
    )
    assert auth.post(auth.client, route + "/disconnect").status_code == 200
    assert worker.post(path, json={"session_id": body["session_id"]}).json()["providers"] == []
    with auth.database.sessions() as session:
        row = session.scalar(select(AccountProviderKey))
        assert row is not None and not row.enabled and not row.encrypted_key
    assert worker.get("/api/v1/account/providers").status_code == 401
    assert own  # Workspace was persisted, rather than inserted into the response fixture.


def test_account_key_fails_closed_without_vault_key(auth: AuthHarness) -> None:
    assert auth.login(auth.client).status_code == 303
    worker = auth.post(auth.client, "administration/node-credentials", {"name": "Fixture"}).json()
    headers = {"Authorization": "Bearer " + worker["token"]}
    auth.client.post("/api/v1/workers/register", json=registration(), headers=headers)
    response = auth.post(
        auth.client,
        "account/providers/anthropic",
        {"api_key": "fixture-hidden", "allowed_node_ids": [worker["node_id"]]},
    )
    assert response.status_code == 503 and "fixture-hidden" not in response.text
    with auth.database.sessions() as session:
        assert session.scalar(select(AccountProviderKey)) is None
