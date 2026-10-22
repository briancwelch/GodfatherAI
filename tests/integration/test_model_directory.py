"""Discover -> allow in workspace -> select agent model, with real persistence and sessions."""

from uuid import UUID

import pytest
from godfather_api.models import Workspace, WorkspaceMember
from godfather_api.scheduler import scheduler_tick
from godfather_contracts import ModelDeployment
from godfather_contracts.model_management import INSTALL_RUNTIME, PROVIDER_RUNTIME_PREFIX
from godfather_model_gateway import NativeModel
from pydantic import SecretStr

from tests.integration.test_authentication import AuthHarness
from tests.integration.test_authentication import auth as auth
from tests.integration.test_nodes import database as database
from tests.integration.test_nodes import registration
from tests.workflow_helpers import sample_definition

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("provider", ["ollama", "openai"])
def test_empty_workspace_can_discover_and_explicitly_use_local_and_api_models(
    auth: AuthHarness, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    auth.settings.provider_vault_key = SecretStr("ab" * 32)
    assert auth.login(auth.client).status_code == 303
    workspace = auth.post(
        auth.client, "administration/workspaces", {"name": "New workspace"}
    ).json()
    credential = auth.post(
        auth.client, "administration/node-credentials", {"name": "Owned computer"}
    ).json()
    worker = auth.browser()
    worker.headers["Authorization"] = "Bearer " + credential["token"]
    body = registration()
    resources = body["resources"]
    assert isinstance(resources, dict)
    resources["source"] = "physical"  # Explicit fixture, no actual provider or hardware.
    body["inference_protocol_version"] = 1
    body["workflow_protocol_version"] = 1
    body["runtimes"] = [
        "account-provider-keys-v1",
        INSTALL_RUNTIME,
        PROVIDER_RUNTIME_PREFIX + "local",
    ]
    local = ModelDeployment(
        provider="ollama", provider_id="local", identifier="qwen3:8b", operations=["chat", "stream"]
    )
    body["model_deployments"] = [local.model_dump(mode="json")]
    assert worker.post("/api/v1/workers/register", json=body).status_code == 200

    async def catalog(*_: object) -> list[NativeModel]:
        return [NativeModel(identifier="gpt-4.1", context_window=8192, max_output_tokens=2048)]

    monkeypatch.setattr("godfather_api.account_providers.discover_catalog", catalog)
    assert (
        auth.post(
            auth.client,
            "account/providers/openai",
            {"api_key": "fixture-secret-key", "allowed_node_ids": [credential["node_id"]]},
        ).status_code
        == 200
    )
    delivered = worker.post(
        f"/api/v1/workers/{credential['node_id']}/account-providers",
        json={"session_id": body["session_id"]},
    ).json()["providers"][0]
    cloud = ModelDeployment(
        provider="openai",
        provider_id=delivered["id"],
        identifier="gpt-4.1",
        operations=["chat", "stream"],
        connection_id=UUID(delivered["connection_id"]),
    )
    body["model_deployments"] = [local.model_dump(mode="json"), cloud.model_dump(mode="json")]
    assert worker.post("/api/v1/workers/register", json=body).status_code == 200
    workspace_id = workspace["id"]
    path = f"/api/v1/models?workspace_id={workspace_id}"
    assert auth.client.get(path).json() == []  # Empty allowlist still denies execution.
    snapshot = auth.client.get(
        f"/api/v1/command-center?section=models&workspace_id={workspace_id}"
    ).json()
    assert {m["deployment"]["provider"] for m in snapshot["models"]} == {"ollama", "openai"}
    assert all(not m["workspace_allowed"] and m["can_enable"] for m in snapshot["models"])
    options = auth.client.get(f"/api/v1/models/install-options?workspace_id={workspace_id}")
    assert options.status_code == 200 and "fixture-secret-key" not in options.text
    assert len(options.json()["models"]) == 2
    assert options.json()["nodes"][0]["installed_models"] == [
        {"identifier": "qwen3:8b", "provider_id": "local"}
    ]
    chosen = local if provider == "ollama" else cloud
    payload = {
        "workspace_id": workspace_id,
        "node_id": credential["node_id"],
        "provider_id": chosen.provider_id,
        "identifier": chosen.identifier,
    }
    assert auth.post(auth.client, "models/workspace-access", payload).status_code == 200
    assert auth.post(auth.client, "models/workspace-access", payload).status_code == 200
    visible = auth.client.get(path).json()
    assert [m["deployment"]["identifier"] for m in visible] == [chosen.identifier]
    with auth.database.sessions() as session:
        row = session.get(Workspace, UUID(workspace_id))
        assert row is not None and row.allowed_models == [chosen.identifier]
        assert row.allowed_tools == []
    spec = sample_definition(chosen.identifier).model_dump(mode="json")
    spec["requirements"]["model_selection"].update(
        provider=chosen.provider,
        connection_id=str(chosen.connection_id) if chosen.connection_id else None,
        paid_consent=provider == "openai",
    )
    spec["workflow"]["steps"] = [
        {"id": "answer", "kind": "model", "output_schema": "text", "instruction": "Answer"}
    ]
    spec["allowed_tools"], spec["permissions"], spec["retry"]["limit"] = [], [], 0
    created = auth.post(auth.client, "agents", {"workspace_id": workspace_id, "definition": spec})
    assert created.status_code == 201, created.text
    run = {
        "workspace_id": workspace_id,
        "agent_id": created.json()["id"],
        "agent_version": 1,
        "input": {"instruction": "Synthetic fixture; never execute"},
        "paid_consent": False,
    }
    if provider == "openai":
        assert auth.post(auth.client, "workflow/jobs", run).status_code == 422
        run["paid_consent"] = True
    submitted = auth.post(auth.client, "workflow/jobs", run)
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["requirements"]["model_selection"]["identifier"] == chosen.identifier
    assert scheduler_tick(auth.database, auth.settings) == 1
    assignment = worker.post(
        f"/api/v1/workers/{credential['node_id']}/jobs/poll",
        json={"session_id": body["session_id"]},
    ).json()["assignment"]
    assert assignment["deployment"]["identifier"] == chosen.identifier
    assert assignment["deployment"]["provider"] == chosen.provider
    # A platform administrator who is only a member cannot expand the workspace policy.
    other = auth.browser()
    assert (
        auth.login(
            other,
            "other",
            "other@example.invalid",
            auth.invite("other@example.invalid", ["platform_admin"]),
        ).status_code
        == 303
    )
    other_id = other.get("/api/v1/auth/me").json()["id"]
    with auth.database.sessions.begin() as session:
        session.add(
            WorkspaceMember(workspace_id=UUID(workspace_id), user_id=UUID(other_id), role="member")
        )
    assert auth.post(other, "models/workspace-access", payload).status_code == 403
    assert (
        auth.post(
            auth.client, "models/workspace-access", {**payload, "identifier": "not-advertised"}
        ).status_code
        == 404
    )
    assert worker.post("/api/v1/models/workspace-access", json=payload).status_code == 401
    if provider == "openai":
        assert auth.post(auth.client, "account/providers/openai/disconnect").status_code == 200
        assert not any(
            m["deployment"]["provider"] == "openai"
            for m in auth.client.get(path + "&include_restricted=true").json()
        )
