"""Project scope, command parsing and desktop execution wiring without host changes."""

import asyncio
import json
import threading
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from godfather_contracts import ModelDeployment, Registration, WorkerAck
from godfather_contracts.coding import CodingSetupOptions, CodingWorkspace
from godfather_worker import cli
from godfather_worker.account_providers import fetch
from godfather_worker.coding_setup import check_project, project_config, setup_options
from godfather_worker.desktop import Contribution, Controller
from godfather_worker.simulated import profile


def test_project_is_owner_and_workspace_scoped_and_uses_literal_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, workspace = uuid4(), uuid4()
    config = project_config(
        name="Project",
        path=str(tmp_path),
        image="sha256:" + "a" * 64,
        owner=owner,
        workspace=workspace,
        patterns="src/*.py, tests/*.py",
        test_command='python -m unittest "tests/test one.py"',
    )
    assert config.allowed_user_ids == [owner] and config.allowed_workspace_ids == [workspace]
    assert config.commands == [["python", "-m", "unittest", "tests/test one.py"]]
    run = Mock(return_value=0)
    monkeypatch.setattr(cli, "main", run)
    controller = Controller(
        {"token": "fixture-secret", "owner_id": str(owner)}, tmp_path / "worker", Mock()
    )
    controller.start(Contribution(repositories=[config], account_providers=True))
    assert controller.thread is not None
    controller.thread.join(2)
    arguments = run.call_args.args[0]
    assert "--execute-workflows" in arguments and "--account-providers" in arguments
    assert "coding.workspace" in arguments and str(workspace) in arguments
    saved = json.loads((tmp_path / "worker/coding.json").read_text())
    assert saved[0]["allowed_user_ids"] == [str(owner)]
    assert "fixture-secret" not in (tmp_path / "worker/settings.json").read_text()
    with pytest.raises(ValueError, match="connected owner"):
        Controller({"token": "x", "owner_id": str(uuid4())}, tmp_path, Mock()).start(
            Contribution(repositories=[config], account_providers=True)
        )
    assert not Contribution().account_providers


def test_project_check_is_read_only_and_rejects_missing_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = project_config(
        name="Project",
        path=str(tmp_path),
        image="sha256:" + "a" * 64,
        owner=uuid4(),
        workspace=uuid4(),
        patterns="*.py",
        test_command="python -m unittest",
    )
    commands = []

    async def command(args: list[str], folder: Path) -> tuple[int, str]:
        commands.append(args)
        return (0, str(tmp_path)) if "--show-toplevel" in args else (1, "")

    monkeypatch.setattr("godfather_worker.coding_setup.command", command)
    with pytest.raises(ValueError, match="Commit"):
        asyncio.run(check_project(config))
    assert all(args[0] == "git" and "rev-parse" in args for args in commands)


def test_workspace_options_reject_wrong_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid4()
    client = Mock()
    client.post_document.return_value = CodingSetupOptions(
        owner_id=owner, workspaces=[CodingWorkspace(id=uuid4(), name="Mine")]
    ).model_dump(mode="json")
    monkeypatch.setattr("godfather_worker.coding_setup.WorkerClient", lambda *_: client)
    with pytest.raises(ValueError, match="owner"):
        setup_options({"token": "fixture", "owner_id": str(uuid4())}, "https://example.invalid")


def test_account_keys_are_memory_only_and_excluded_from_serialization() -> None:
    client = Mock()
    client.post_document.return_value = {
        "providers": [
            {
                "id": "account-fixture",
                "provider": "openai",
                "connection_id": str(uuid4()),
                "model_catalog": [],
                "api_key": "fixture-private-key",
            }
        ]
    }
    config = fetch(client, uuid4(), uuid4())[0]
    assert config.headers()["Authorization"] == "Bearer fixture-private-key"
    assert "fixture-private-key" not in config.model_dump_json() + repr(config)


def test_worker_refresh_advertises_account_models_without_local_provider_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = threading.Event()
    node_id = uuid4()
    client = Mock()
    registrations = []

    def post(path: str, payload: Registration) -> WorkerAck:
        registrations.append(payload)
        if len(registrations) == 2:
            stop.set()
        return WorkerAck(
            node_id=node_id,
            state="online",
            connection_status="online",
            heartbeat_interval_seconds=10,
        )

    client.post.side_effect = post
    client.post_document.return_value = {"assignment": None, "provider_checks": []}
    config_client = Mock()
    config_client.post_document.return_value = {
        "providers": [
            {
                "id": "account-fixture",
                "provider": "openai",
                "connection_id": str(uuid4()),
                "model_catalog": [],
                "api_key": "fixture-private-key",
            }
        ]
    }
    configs = fetch(config_client, node_id, uuid4())
    monkeypatch.setattr("godfather_worker.account_providers.fetch", lambda *_: configs)
    monkeypatch.setattr(cli, "discover", lambda: profile("LV-01"))

    async def models(configurations: object) -> list[ModelDeployment]:
        return [
            ModelDeployment(
                provider_id="account-fixture",
                provider="openai",
                connection_id=configs[0].connection_id,
                identifier="gpt-4.1",
            )
        ]

    monkeypatch.setattr(cli, "discover_models", models)
    assert (
        cli.main(
            ["--account-providers"],
            credential={"kind": "worker", "token": "fixture"},
            stop_event=stop,
            observer=Mock(),
            worker_client=client,
        )
        == 0
    )
    assert len(registrations) == 2
    assert registrations[-1].model_deployments[0].identifier == "gpt-4.1"
    assert "account-provider-keys-v1" in registrations[-1].runtimes
