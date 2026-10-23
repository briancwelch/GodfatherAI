"""Isolated desktop tests; no physical Mac, Keychain or inference acceptance implied."""

import json
import plistlib
import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from godfather_contracts import Heartbeat, Registration, WorkerAck
from godfather_contracts.model_management import INSTALL_RUNTIME, PROVIDER_RUNTIME_PREFIX
from godfather_worker import cli, keychain
from godfather_worker.desktop import (
    Contribution,
    Controller,
    LimitedClient,
    Pairing,
    first_run_contribution,
    login_startup,
)
from godfather_worker.simulated import profile

from scripts import build_macos_worker


def test_pairing_keeps_secrets_out_of_browser_and_saves_only_to_store() -> None:
    pairing = Pairing()
    assert pairing.secret not in pairing.browser_url
    assert pairing.machine_secret not in pairing.browser_url
    assert pairing.secret not in repr(pairing)
    transport = Mock()
    transport.post_document.return_value = {
        "credential_id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "00000000-0000-0000-0000-000000000002",
        "owner": "test@example.invalid",
        "name": "Mac",
    }
    store = Mock()
    result = pairing.exchange(store, transport)
    assert result["token"] == pairing.machine_secret
    assert json.loads(store.write.call_args.args[0]) == result
    assert transport.post_document.call_args.args[0] == "/api/v1/workers/enrollment/exchange"


def test_failed_exchange_never_writes_identity() -> None:
    store, transport = Mock(), Mock()
    transport.post_document.side_effect = OSError("lost response")
    with pytest.raises(OSError):
        Pairing().exchange(store, transport)
    store.write.assert_not_called()


def test_keychain_failure_is_not_replaced_with_plaintext() -> None:
    store, transport = Mock(), Mock()
    transport.post_document.return_value = {
        "credential_id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "00000000-0000-0000-0000-000000000002",
    }
    store.write.side_effect = OSError("Keychain locked")
    with pytest.raises(OSError, match="Keychain"):
        Pairing().exchange(store, transport)


def test_keychain_uses_in_process_native_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("godfather_worker.keychain.platform.system", lambda: "Darwin")
    native = Mock()
    native.SecKeychainAddGenericPassword.return_value = 0
    native.SecKeychainFindGenericPassword.return_value = keychain.NOT_FOUND
    monkeypatch.setattr("godfather_worker.keychain.c.CDLL", lambda _: native)
    store = keychain.Keychain()
    store.write("secret-kept-in-memory")
    assert native.SecKeychainAddGenericPassword.call_args.args[6] == b"secret-kept-in-memory"
    assert store.read() is None
    native.SecKeychainAddGenericPassword.return_value = -1
    with pytest.raises(OSError, match="Keychain"):
        store.write("not-written-to-disk")


@pytest.mark.parametrize(
    "system,machine", [("Windows", "AMD64"), ("Linux", "x86_64"), ("Darwin", "i386")]
)
def test_installer_refuses_non_native_targets(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str
) -> None:
    monkeypatch.setattr("scripts.build_macos_worker.platform.system", lambda: system)
    monkeypatch.setattr("scripts.build_macos_worker.platform.machine", lambda: machine)
    with pytest.raises(RuntimeError, match="native"):
        build_macos_worker.build("0.1.0-rc.6")


@pytest.mark.parametrize("machine", ["arm64", "x86_64"])
def test_native_architecture_detected(monkeypatch: pytest.MonkeyPatch, machine: str) -> None:
    monkeypatch.setattr("scripts.build_macos_worker.platform.system", lambda: "Darwin")
    monkeypatch.setattr("scripts.build_macos_worker.platform.machine", lambda: machine)
    assert build_macos_worker.native_architecture() == machine


def test_contribution_limits_registration_and_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[object] = []
    monkeypatch.setattr(
        "godfather_worker.desktop.WorkerClient.post_document",
        lambda self, path, payload: sent.append(payload),
    )
    registration = Registration(
        **profile("LA-01").model_dump(), session_id="00000000-0000-0000-0000-000000000001"
    )
    client = LimitedClient("secret", Contribution(cpu_cores=1, ram_gib=2))
    client.post_document("register", registration)
    client.post_document(
        "heartbeat", Heartbeat(session_id=registration.session_id, resources=registration.resources)
    )
    for payload in sent:
        assert isinstance(payload, (Registration, Heartbeat))
        assert payload.resources.cpu_count == 1
        assert payload.resources.ram_bytes == 2 * 1024**3
        assert not payload.resources.gpus
    assert registration.resources.cpu_count > 1  # Never mutate discovery inventory.


def test_controller_starts_existing_protocol_without_credential_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started, finished = threading.Event(), threading.Event()
    calls: list[dict[str, object]] = []

    def run(arguments: list[str], **kwargs: object) -> int:
        calls.append({"arguments": arguments, **kwargs})
        started.set()
        event = kwargs["stop_event"]
        assert isinstance(event, threading.Event)
        event.wait(2)
        finished.set()
        return 0

    monkeypatch.setattr(cli, "main", run)
    identity = {"kind": "worker", "token": "secret"}
    controller = Controller(identity, tmp_path, Mock())
    controller.start(Contribution())
    assert started.wait(2)
    assert "--credential-file" not in str(calls[0]["arguments"])
    assert calls[0]["credential"] == identity
    assert "secret" not in (tmp_path / "settings.json").read_text()
    controller.stop()
    assert finished.wait(2)
    assert controller.thread is not None
    controller.thread.join(2)
    assert not controller.running
    controller.start(Contribution())  # Same saved identity on restart.
    controller.stop()
    assert controller.thread is not None
    controller.thread.join(2)


def test_shared_work_requires_explicit_both_allowlists(tmp_path: Path) -> None:
    controller = Controller({"token": "secret"}, tmp_path, Mock())
    with pytest.raises(ValueError, match="explicit"):
        controller.start(Contribution(shared=True))
    assert not controller.running


def test_fresh_install_can_contribute_without_ids_but_existing_defaults_stay_private() -> None:
    existing = Contribution.model_validate({"inference": False, "cpu_cores": 1, "ram_gib": 2})
    assert not existing.share_with_workspaces and not existing.shared
    fresh = first_run_contribution(profile("LA-01").resources)
    assert fresh.shared and fresh.share_with_workspaces and fresh.inference
    assert fresh.allowed_owner_ids == fresh.allowed_workspace_ids == []
    assert fresh.cpu_cores == profile("LA-01").resources.cpu_count
    assert not fresh.account_providers and not fresh.model_installation
    assert not fresh.runtime_installation and not fresh.repositories and not fresh.workloads
    private = fresh.with_workspace_contribution(False)
    assert not private.shared and not private.share_with_workspaces
    assert private.inference  # The owner's own local jobs still work.


def test_workspace_contribution_keeps_credentials_and_downloads_separate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run = Mock(return_value=0)
    monkeypatch.setattr(cli, "main", run)
    controller = Controller({"kind": "worker", "token": "fixture"}, tmp_path, Mock())
    controller.start(Contribution().with_workspace_contribution(True))
    assert controller.thread is not None
    controller.thread.join(2)
    arguments = run.call_args.args[0]
    assert "--share-with-workspaces" in arguments
    assert "--execute-workflows" in arguments and "--inference-config" in arguments
    assert "--allow-owner" not in arguments and "--allow-workspace" not in arguments
    assert "--account-providers" not in arguments and "--allow-model-installation" not in arguments
    assert (
        "--allow-tool-permission" not in arguments
        and "--allow-runtime-installation" not in arguments
    )


def test_legacy_registration_omits_new_sharing_field() -> None:
    registration = Registration(
        **profile("LA-01").model_dump(), session_id="00000000-0000-0000-0000-000000000001"
    )
    assert "share_with_workspaces" not in registration.model_dump(mode="json")
    assert (
        registration.model_copy(update={"share_with_workspaces": True}).model_dump(mode="json")[
            "share_with_workspaces"
        ]
        is True
    )


def test_contribution_change_applies_when_idle_without_cancelling_the_current_job(
    tmp_path: Path,
) -> None:
    pytest.importorskip(
        "tkinter",
        reason="Native Tk lifecycle is covered by desktop packaging jobs",
        exc_type=ImportError,
    )
    from godfather_worker.desktop_app import Application

    app = object.__new__(Application)
    app.folder, app.settings, app.identity = tmp_path, Contribution(), {"token": "fixture"}
    app.contribute, app.inference, app.model_installation = Mock(), Mock(), Mock()
    app.account_connections, app.shared, app.status = Mock(), Mock(), Mock()
    app.controller = Mock(running=True, maintenance_event=threading.Event())
    app.settings_restart_pending, app.closing = False, False
    app.start = Mock()  # type: ignore[method-assign]
    app.apply_settings(app.settings.with_workspace_contribution(True), start=True)
    assert app.settings_restart_pending and app.controller.maintenance_event.is_set()
    app.controller.stop.assert_not_called()
    app.start.assert_not_called()
    saved = Contribution.model_validate_json((tmp_path / "settings.json").read_text())
    assert saved.share_with_workspaces and saved.inference
    app.controller.running = False
    app.restart_after_settings()
    app.start.assert_called_once()
    assert not app.settings_restart_pending


@pytest.mark.parametrize("host", ["LV-01", "LA-01", "LA-02"])
@pytest.mark.parametrize("downloads", [False, True])
@pytest.mark.parametrize("workspace_sharing", [False, True])
def test_desktop_download_consent_reaches_registration_with_empty_inventory(
    host: str,
    downloads: bool,
    workspace_sharing: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Desktop -> real CLI -> registration; no coordinator or model traffic."""
    monkeypatch.setattr(cli, "discover", lambda: profile(host))

    async def empty_models(*_: object) -> list[object]:
        return []

    monkeypatch.setattr(cli, "discover_models", empty_models)
    registrations: list[Registration] = []
    ack = WorkerAck(
        node_id="00000000-0000-0000-0000-000000000001",
        state="online",
        connection_status="online",
        heartbeat_interval_seconds=10,
    )

    def register(self: LimitedClient, path: str, payload: Registration) -> WorkerAck:
        assert path == "/api/v1/workers/register"
        registrations.append(payload)
        return ack

    def poll(self: LimitedClient, path: str, payload: object) -> object:
        assert path.endswith("/jobs/poll")
        controller.stop_event.set()
        return {"assignment": None}

    monkeypatch.setattr(LimitedClient, "post", register)
    monkeypatch.setattr(LimitedClient, "post_document", poll)
    controller = Controller({"kind": "worker", "token": "fixture-only"}, tmp_path, Mock())
    settings = Contribution(inference=True, model_installation=downloads)
    if workspace_sharing:
        settings = settings.with_workspace_contribution(True)
    controller.start(settings)
    assert controller.thread is not None
    controller.thread.join(3)
    assert not controller.running
    assert len(registrations) == 1
    registration = registrations[0]
    assert not registration.model_deployments
    assert registration.workflow_protocol_version == 1
    assert registration.share_with_workspaces is workspace_sharing
    assert not registration.allowed_job_owner_ids and not registration.allowed_workspace_ids
    assert registration.worker_tools == [] and registration.tool_permissions == []
    assert (INSTALL_RUNTIME in registration.runtimes) is downloads
    assert (PROVIDER_RUNTIME_PREFIX + "local-ollama" in registration.runtimes) is downloads
    saved = Contribution.model_validate_json((tmp_path / "settings.json").read_text())
    assert saved.model_installation is downloads


def test_desktop_download_consent_is_separate_and_requires_local_models(tmp_path: Path) -> None:
    assert not Contribution().model_installation
    assert not Contribution.model_validate({"inference": True}).model_installation
    controller = Controller({"token": "fixture-only"}, tmp_path, Mock())
    with pytest.raises(ValueError, match="Enable local AI models"):
        controller.start(Contribution(model_installation=True))
    assert not controller.running
    assert not (tmp_path / "settings.json").exists()


def test_desktop_account_models_enable_read_only_workflows_without_local_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Mock(return_value=0)
    monkeypatch.setattr(cli, "main", run)
    controller = Controller({"kind": "worker", "token": "fixture"}, tmp_path, Mock())
    controller.start(Contribution(account_providers=True))
    assert controller.thread is not None
    controller.thread.join(2)
    arguments = run.call_args.args[0]
    assert "--execute-workflows" in arguments and "--account-providers" in arguments
    assert "--inference-config" not in arguments
    assert "--allow-tool" not in arguments and "--allow-tool-permission" not in arguments


def test_cloud_images_require_separate_owner_opt_in_and_no_local_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Mock(return_value=0)
    monkeypatch.setattr(cli, "main", run)
    controller = Controller({"kind": "worker", "token": "fixture"}, tmp_path, Mock())
    with pytest.raises(ValueError, match="Enable account API connections"):
        controller.start(Contribution(cloud_images=True))
    assert not (tmp_path / "settings.json").exists()
    controller.start(Contribution(account_providers=True, cloud_images=True))
    assert controller.thread is not None
    controller.thread.join(2)
    arguments = run.call_args.args[0]
    assert "--execute-workflows" in arguments and "--cloud-images" in arguments
    assert "--account-providers" in arguments and "images.generate" in arguments
    assert "--inference-config" not in arguments and "--workload-config" not in arguments


def test_login_agent_only_product_file_and_no_root(tmp_path: Path) -> None:
    executable = tmp_path / "App.app/Contents/MacOS/worker"
    executable.parent.mkdir(parents=True)
    executable.touch()
    agent = tmp_path / "LaunchAgents/ai.the-godfather.worker.plist"
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("preserve")
    login_startup(True, executable, agent)
    assert agent.exists() and "KeepAlive" in agent.read_text()
    assert plistlib.loads(agent.read_bytes())["ProgramArguments"] == [str(executable), "--login"]
    login_startup(False, executable, agent)
    assert not agent.exists() and unrelated.read_text() == "preserve"


def test_native_packaging_commands_and_versioned_checksum(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Fake native commands test build orchestration, not a real Mac executable."""
    monkeypatch.setattr(build_macos_worker, "ROOT", tmp_path)
    monkeypatch.setattr(build_macos_worker, "native_architecture", lambda: "arm64")
    monkeypatch.setattr("scripts.build_macos_worker.build_worker.build", lambda _: None)
    link = Mock()
    monkeypatch.setattr(Path, "symlink_to", link)
    cli_output = tmp_path / "dist/consigliere-0.1.0-rc.6-macos-arm64"
    cli_output.mkdir(parents=True)
    (cli_output / "manifest.json").write_text(json.dumps({"source_revision": "a" * 40}))
    workspace = tmp_path / ".cache/worker-build/0.1.0-rc.6-macos-arm64"
    workspace.mkdir(parents=True)
    docs = tmp_path / "packages/worker/macos"
    docs.mkdir(parents=True)
    for name in ("README.md", "TROUBLESHOOTING.md", "ADMINISTRATOR.md"):
        (docs / name).write_text("guide")
    commands: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        if "PyInstaller" in arguments:
            app = workspace / "app/Consigliere.app/Contents"
            (app / "MacOS").mkdir(parents=True)
            (app / "MacOS/Consigliere").write_bytes(b"mock-native-executable")
            (app / "Info.plist").write_bytes(
                plistlib.dumps({"CFBundleIdentifier": "ai.the-godfather.worker"})
            )
        if arguments[0] == "/usr/bin/hdiutil":
            Path(arguments[-1]).write_bytes(b"mock-dmg-not-a-native-acceptance-artifact")
        return subprocess.CompletedProcess(
            arguments, 0, stdout="arm64" if "lipo" in arguments[0] else ""
        )

    monkeypatch.setattr("scripts.build_macos_worker.subprocess.run", run)
    dmg = build_macos_worker.build("0.1.0-rc.6")
    assert dmg.name == "consigliere-0.1.0-rc.6-macos-arm64-installer.dmg"
    assert Path(str(dmg) + ".sha256").read_text().endswith(dmg.name + "\n")
    assert "Ad-hoc" in Path(str(dmg) + ".manifest.json").read_text()
    assert (dmg.with_suffix("") / "Install Consigliere.command").is_file()
    assert any("--self-test" in command for command in commands)
    assert not any("notarytool" in command for command in commands)
    with pytest.raises(RuntimeError, match="already exists"):
        build_macos_worker.build("0.1.0-rc.6")
