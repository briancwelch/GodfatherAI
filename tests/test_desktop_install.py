"""Installer recovery and download verification without changing the host."""

import json
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest
from godfather_worker import windows_setup
from godfather_worker.windows_setup import install

from scripts.release import sha256
from scripts.stage_worker_downloads import stage


def test_per_user_install_preserves_identity_and_repeats_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text('{"version":"1.2.3"}')
    (source / "godfather-worker.exe").write_bytes(b"synthetic executable")
    local = tmp_path / "local"
    local.mkdir()
    identity = local / "private-existing-identity"
    identity.write_text("preserve")
    command = Mock()
    monkeypatch.setattr("godfather_worker.windows_setup.update_startup", Mock())
    monkeypatch.setattr("godfather_worker.windows_setup.subprocess.run", command)
    executable = install(source, local, tmp_path / "programs")
    assert executable.read_bytes() == b"synthetic executable"
    assert command.call_args.kwargs["env"]["GODFATHER_SETUP_TARGET"] == str(executable)
    assert install(source, local, tmp_path / "programs") == executable
    executable.write_bytes(b"existing different build")
    with pytest.raises(OSError, match="different files"):
        install(source, local, tmp_path / "programs")
    assert executable.read_bytes() == b"existing different build"
    assert identity.read_text() == "preserve"


def test_automatic_update_waits_for_worker_and_retains_owner_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip(
        "tkinter", reason="native setup entry point requires the optional Tk adapter"
    )
    source = tmp_path / "worker-payload"
    source.mkdir()
    (source / "manifest.json").write_text('{"version":"1.2.4"}')
    (source / "consigliere.exe").write_bytes(b"new application fixture")
    local, roaming = tmp_path / "local", tmp_path / "roaming"
    data = local / "The Godfather/Desktop Worker"
    data.mkdir(parents=True)
    identity = data / "settings.json"
    identity.write_text("owner-data-preserved")
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr("sys.argv", ["setup", "--auto-update", "--wait-pid", "12345"])
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    wait, launched = Mock(), Mock()
    monkeypatch.setattr("godfather_worker.updates.wait_for_previous", wait)
    monkeypatch.setattr(windows_setup, "create_shortcut", Mock())
    monkeypatch.setattr(windows_setup, "update_startup", Mock())
    monkeypatch.setattr("godfather_worker.windows_setup.subprocess.Popen", launched)
    assert windows_setup.main() == 0
    wait.assert_called_once()
    assert identity.read_text() == "owner-data-preserved"
    assert Path(launched.call_args.args[0][0]).read_bytes() == b"new application fixture"


def test_interrupted_install_can_be_retried_without_partial_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text('{"version":"1.2.3"}')
    (source / "godfather-worker.exe").write_bytes(b"synthetic")
    actual_copy = shutil.copytree

    def partial_copy(src: Path, dst: Path) -> None:
        dst.mkdir()
        (dst / "partial").write_text("incomplete")
        raise OSError("test disk full")

    monkeypatch.setattr("godfather_worker.windows_setup.shutil.copytree", partial_copy)
    with pytest.raises(OSError, match="disk full"):
        install(source, tmp_path / "local", tmp_path / "programs")
    version = tmp_path / "local/The Godfather/Desktop Worker/app"
    assert not version.exists()
    monkeypatch.setattr("godfather_worker.windows_setup.shutil.copytree", actual_copy)
    monkeypatch.setattr("godfather_worker.windows_setup.subprocess.run", Mock())
    monkeypatch.setattr("godfather_worker.windows_setup.update_startup", Mock())
    assert install(source, tmp_path / "local", tmp_path / "programs").is_file()


def test_download_staging_checks_checksum_before_publishing(tmp_path: Path) -> None:
    installer = tmp_path / "godfather-worker-1.2.3-windows-x64-setup.exe"
    installer.write_bytes(b"synthetic installer")
    Path(str(installer) + ".manifest.json").write_text(
        json.dumps({"version": "1.2.3", "signing": "unsigned test"})
    )
    checksum = Path(str(installer) + ".sha256")
    checksum.write_text("incorrect")
    output = tmp_path / "downloads"
    with pytest.raises(ValueError, match="checksum"):
        stage([installer], output)
    assert not output.exists()
    checksum.write_text(f"{sha256(installer)}  {installer.name}\n")
    stage([installer], output)
    entry = json.loads((output / "manifest.json").read_text())["artifacts"][0]
    assert entry["signing"] == "unsigned test"
    assert sha256(output / entry["filename"]) == entry["sha256"]
