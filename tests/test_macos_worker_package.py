"""Package rejection checks; native execution belongs to the macOS workflow."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.check_macos_worker import inspect_bundle, verify_checksum
from scripts.release import sha256


def test_checksum_detects_modified_package(tmp_path: Path) -> None:
    dmg = tmp_path / "candidate.dmg"
    dmg.write_bytes(b"original candidate")
    Path(str(dmg) + ".sha256").write_text(f"{sha256(dmg)}  {dmg.name}\n")
    verify_checksum(dmg)
    dmg.write_bytes(b"modified candidate")
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify_checksum(dmg)


@pytest.mark.parametrize("name", [".env", "production.env", "credentials.json", "identity.p12"])
def test_local_secret_inputs_are_rejected(tmp_path: Path, name: str) -> None:
    (tmp_path / name).touch()
    with pytest.raises(RuntimeError, match="Forbidden build input"):
        inspect_bundle(tmp_path, "arm64")


def test_empty_app_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no native binaries"):
        inspect_bundle(tmp_path, "arm64")


def test_build_host_runtime_dependency_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "native-library").write_bytes(bytes.fromhex("cffaedfe"))
    commands = Mock(
        side_effect=[
            "arm64\n",
            "library:\n\t/opt/homebrew/lib/libtk.dylib (compatibility version 1)\n",
        ]
    )
    monkeypatch.setattr("scripts.check_macos_worker.execute", commands)
    with pytest.raises(RuntimeError, match="External runtime dependency"):
        inspect_bundle(tmp_path, "arm64")


def test_wrong_library_architecture_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "native-library").write_bytes(bytes.fromhex("cffaedfe"))
    monkeypatch.setattr("scripts.check_macos_worker.execute", lambda *args: "x86_64\n")
    with pytest.raises(RuntimeError, match="Wrong native library architecture"):
        inspect_bundle(tmp_path, "arm64")
