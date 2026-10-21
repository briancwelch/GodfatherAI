"""Safe app replacement and optional local-network discovery regressions."""

import json
import plistlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from godfather_worker import tailscale, windows_setup
from godfather_worker.app_installation import replace_payload
from godfather_worker.macos_setup import BUNDLE_ID
from godfather_worker.macos_setup import install as install_mac


def payload(folder: Path, version: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"version": version, "target": "windows-x64"}))
    (folder / "godfather-worker.exe").write_bytes(version.encode())
    return folder


def test_windows_upgrade_keeps_one_app_and_preserves_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(windows_setup, "create_shortcut", Mock())
    monkeypatch.setattr(windows_setup, "update_startup", Mock())
    base = tmp_path / "local/The Godfather/Desktop Worker"
    payload(base / "versions/0.3.2-rc.1", "0.3.2-rc.1")
    (base / "settings.json").write_text('"preserve-project-permissions"')
    (tmp_path / "programs").mkdir()
    (tmp_path / "programs/The Godfather Worker.lnk").touch()
    first = windows_setup.install(
        payload(tmp_path / "first", "0.3.3-rc.1"), tmp_path / "local", tmp_path / "programs"
    )
    second = windows_setup.install(
        payload(tmp_path / "second", "0.3.3-rc.2"), tmp_path / "local", tmp_path / "programs"
    )
    assert first == second == base / "app/godfather-worker.exe"
    assert second.read_bytes() == b"0.3.3-rc.2"
    assert list((base / "versions").iterdir()) == []
    assert not (tmp_path / "programs/The Godfather Worker.lnk").exists()
    assert (base / "settings.json").read_text() == '"preserve-project-permissions"'


def test_windows_running_app_blocks_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(windows_setup, "acquire_lock", lambda _: None)
    with pytest.raises(OSError, match="Quit Consigliere"):
        windows_setup.install(
            payload(tmp_path / "new", "0.3.3-rc.1"), tmp_path / "local", tmp_path / "programs"
        )


@pytest.mark.parametrize("registered", ["owned", "unrelated", "absent"])
def test_upgrade_preserves_existing_startup_consent(
    registered: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = MagicMock()
    base = tmp_path / "The Godfather/Desktop Worker"
    old = (
        base / "versions/0.3.2-rc.1/godfather-worker.exe"
        if registered == "owned"
        else tmp_path / "other.exe"
    )
    registry.QueryValueEx.return_value = (f'"{old}" --login', 1)
    if registered == "absent":
        registry.QueryValueEx.side_effect = FileNotFoundError
    monkeypatch.setattr(
        "godfather_worker.windows_setup.importlib.import_module", lambda _: registry
    )
    replacement = base / "app/consigliere.exe"
    windows_setup.update_startup(base, replacement)
    if registered == "owned":
        assert registry.SetValueEx.call_args.args[-1] == f'"{replacement}" --login'
    else:
        registry.SetValueEx.assert_not_called()


def test_windows_unknown_legacy_folder_is_never_deleted(tmp_path: Path) -> None:
    unknown = tmp_path / "local/The Godfather/Desktop Worker/versions/my-files"
    unknown.mkdir(parents=True)
    (unknown / "notes.txt").write_text("keep")
    with pytest.raises(OSError, match="Unrecognized"):
        windows_setup.install(
            payload(tmp_path / "new", "0.3.3-rc.1"), tmp_path / "local", tmp_path / "programs"
        )
    assert (unknown / "notes.txt").read_text() == "keep"


def test_failed_swap_restores_old_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = payload(tmp_path / "app", "0.3.2-rc.1")
    incoming = payload(tmp_path / "new", "0.3.3-rc.1")
    rename = Path.rename

    def fail_staged(path: Path, target: Path) -> Path:
        if path.name == "payload":
            raise OSError("simulated failed swap")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_staged)
    with pytest.raises(OSError, match="simulated"):
        replace_payload(incoming, original)
    assert (original / "godfather-worker.exe").read_bytes() == b"0.3.2-rc.1"


def test_mac_rename_and_upgrade_keep_one_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source/Consigliere.app"
    for app in (source, tmp_path / "Applications/The Godfather Worker.app"):
        (app / "Contents").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": BUNDLE_ID}))
    (source / "Contents/version").write_text("one")
    target = install_mac(source, tmp_path / "Applications")
    (source / "Contents/version").write_text("two")
    assert install_mac(source, tmp_path / "Applications") == target
    assert (target / "Contents/version").read_text() == "two"
    assert [p.name for p in target.parent.iterdir()] == ["Consigliere.app"]


@pytest.mark.parametrize(
    "document,connected",
    [
        ({"BackendState": "Running", "Self": {"Online": True}}, True),
        ({"BackendState": "Stopped", "Self": {"Online": True}}, False),
        ({"BackendState": "NeedsLogin"}, False),
        ({"BackendState": "Running", "Self": {"Online": False}}, False),
    ],
)
def test_tailscale_read_only_status(
    document: dict[str, object], connected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tailscale, "executable", lambda: "fixture-tailscale")
    run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(document)))
    monkeypatch.setattr("godfather_worker.tailscale.subprocess.run", run)
    status = tailscale.detect()
    assert status.installed and status.connected is connected
    assert run.call_args.args[0] == ["fixture-tailscale", "status", "--json", "--peers=false"]
    assert run.call_args.kwargs["env"]["TAILSCALE_BE_CLI"] == "1"
    assert run.call_args.kwargs["timeout"] == 5


def test_no_tailscale_never_blocks_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tailscale, "executable", lambda: None)
    run = Mock()
    monkeypatch.setattr("godfather_worker.tailscale.subprocess.run", run)
    assert not tailscale.detect().installed
    run.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [OSError("denied"), subprocess.TimeoutExpired("fixture", 5), ValueError("invalid json")],
)
def test_tailscale_failures_leave_https_available(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tailscale, "executable", lambda: "fixture-tailscale")
    monkeypatch.setattr("godfather_worker.tailscale.subprocess.run", Mock(side_effect=error))
    assert "HTTPS remains available" in tailscale.detect().message


@pytest.mark.parametrize(
    "system,location",
    [
        ("Windows", "C:/Program Files/Tailscale/tailscale.exe"),
        ("Darwin", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"),
        ("Linux", "/usr/bin/tailscale"),
    ],
)
def test_tailscale_not_on_path_still_detected(
    system: str, location: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("godfather_worker.tailscale.shutil.which", lambda _: None)
    monkeypatch.setattr("godfather_worker.tailscale.platform.system", lambda: system)
    monkeypatch.setattr(Path, "is_file", lambda path: path.as_posix() == location)
    monkeypatch.setenv("PROGRAMFILES", "C:/Program Files")
    assert Path(tailscale.executable() or "missing").as_posix() == location
