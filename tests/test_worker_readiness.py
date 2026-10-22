"""Update trust, local runtime consent and archive safety without host installations."""

import asyncio
import hashlib
import io
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from godfather_model_gateway import ProviderConfig
from godfather_worker import local_runtime, updates
from godfather_worker.desktop_theme import Preferences


def test_semantic_updates_are_platform_specific_and_never_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [
        {"filename": f"consigliere-{v}-{target}", "sha256": "a" * 64}
        for v, target in [
            ("1.2.3-rc.9", "windows-x64-setup.exe"),
            ("1.2.3-rc.10", "windows-x64-setup.exe"),
            ("9.0.0", "macos-arm64-installer.dmg"),
            ("1.0.0", "linux-x64.zip"),
        ]
    ]
    monkeypatch.setattr(updates, "read_manifest", lambda *args: {"artifacts": entries})
    result = updates.available_update("https://example.invalid", "1.2.3-rc.9", "windows-x64")
    assert result and result["version"] == "1.2.3-rc.10"
    assert updates.available_update("https://example.invalid", "1.2.3", "windows-x64") is None
    assert updates.available_update("https://example.invalid", "10.0.0", "macos-arm64") is None
    assert Preferences().automatic_updates is False


def test_update_hash_failure_removes_partial_file_and_never_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = {
        "filename": "consigliere-1.2.3-windows-x64-setup.exe",
        "version": "1.2.3",
        "sha256": hashlib.sha256(b"trusted").hexdigest(),
    }
    monkeypatch.setattr(updates, "available_update", lambda *args: item)
    transport = Mock()
    transport.url = "https://example.invalid"
    transport.opener.open.return_value = io.BytesIO(b"tampered")
    monkeypatch.setattr(updates, "WorkerClient", lambda *args: transport)
    with pytest.raises(ValueError, match="checksum"):
        updates.download_update(transport.url, item, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_changed_manifest_refuses_download_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updates, "available_update", lambda *args: None)
    with pytest.raises(ValueError, match="published update changed"):
        updates.download_update("https://example.invalid", {"filename": "stale"}, tmp_path)


def test_missing_platform_download_is_unknown_not_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(updates, "read_manifest", lambda *args: {"artifacts": []})
    with pytest.raises(ValueError, match="No compatible worker download"):
        updates.available_update("https://example.invalid", "1.2.3", "windows-x64")


def test_waiting_update_is_rehashed_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = tmp_path / "consigliere-update.exe"
    installer.write_bytes(b"changed while waiting for job")
    launched = Mock()
    monkeypatch.setattr("godfather_worker.updates.subprocess.Popen", launched)
    with pytest.raises(ValueError, match="checksum changed"):
        updates.launch_update(installer, "a" * 64)
    launched.assert_not_called()


def test_model_setup_cannot_install_without_local_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(config: ProviderConfig) -> bool:
        return False

    monkeypatch.setattr(local_runtime, "ready", unavailable)
    monkeypatch.setattr("godfather_worker.local_runtime.shutil.which", lambda *args: None)
    installer = Mock()
    monkeypatch.setattr(local_runtime, "install_runtime", installer)
    with pytest.raises(ValueError, match="Approve local runtime setup"):
        asyncio.run(
            local_runtime.ensure_runtime(
                "https://example.invalid",
                tmp_path,
                ProviderConfig(id="local-ollama", provider="ollama"),
                False,
            )
        )
    installer.assert_not_called()


@pytest.mark.parametrize("name", ["../escape.exe", "/absolute.exe"])
def test_runtime_archive_rejects_traversal(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(name, b"not executable")
    with pytest.raises(ValueError, match="Unsafe runtime archive"):
        local_runtime.extract_runtime(archive, tmp_path / "output")
    assert not (tmp_path / "escape.exe").exists()


def test_runtime_file_is_staged_without_executing_it(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("ollama.exe", b"synthetic archive fixture")
    executable = local_runtime.extract_runtime(archive, tmp_path / "output")
    assert executable.read_bytes() == b"synthetic archive fixture"


def test_managed_runtime_pointer_cannot_escape_owner_folder(tmp_path: Path) -> None:
    runtime = tmp_path / "local-runtime"
    runtime.mkdir()
    (tmp_path / "other.exe").write_bytes(b"not executed")
    (runtime / "current.txt").write_text("../other.exe")
    assert local_runtime.managed_executable(tmp_path) is None


def test_runtime_redirect_rejects_http_and_untrusted_hosts() -> None:
    from urllib.request import Request

    for url in ("http://github.com/ollama/ollama", "https://evil.example/payload"):
        with pytest.raises(ValueError, match="Untrusted runtime download redirect"):
            local_runtime.OfficialRedirect().redirect_request(
                Request("https://github.com/ollama/ollama"), None, 302, "", {}, url
            )


def test_old_model_download_wire_format_remains_compatible() -> None:
    from uuid import uuid4

    from godfather_contracts.model_management import ModelInstallInput

    payload = ModelInstallInput(node_id=uuid4(), provider_id="local", identifier="qwen3:0.6b")
    assert "install_runtime" not in payload.model_dump(mode="json")
    assert (
        payload.model_copy(update={"install_runtime": True}).model_dump()["install_runtime"] is True
    )


def test_maintenance_finishes_claimed_work_before_exiting(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    from godfather_contracts import WorkerAck
    from godfather_worker import cli

    from tests.test_model_installation import fixture

    assignment, _ = fixture()
    maintenance, cancelled = threading.Event(), threading.Event()
    ack = WorkerAck(
        node_id="12345678-1234-1234-1234-123456789abc",
        state="online",
        connection_status="online",
        heartbeat_interval_seconds=10,
    )
    completed: list[str] = []
    transport = Mock()
    transport.post.return_value = ack

    def poll(*args: object) -> dict[str, object]:
        maintenance.set()  # Request arrives while a claim is in flight.
        return {"assignment": assignment.model_dump(mode="json"), "provider_checks": []}

    transport.post_document.side_effect = poll

    def execute(*args: object) -> None:
        assert not cancelled.is_set()
        completed.append("finished")

    monkeypatch.setattr(cli, "execute", execute)
    assert (
        cli.main(
            ["--simulate", "LV-01", "--execute-synthetic"],
            credential={"kind": "worker", "token": "fixture"},
            worker_client=transport,
            stop_event=cancelled,
            maintenance_event=maintenance,
            observer=Mock(),
        )
        == 0
    )
    assert completed == ["finished"] and not cancelled.is_set()
    assert transport.post_document.call_count == 1
