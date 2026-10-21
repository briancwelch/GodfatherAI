"""Isolated desktop tests; no physical Mac, Keychain or inference acceptance implied."""

import json
import plistlib
import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from godfather_contracts import Heartbeat, Registration
from godfather_worker import cli, keychain
from godfather_worker.desktop import Contribution, Controller, LimitedClient, Pairing, login_startup
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
