"""Release security boundaries and immutable packaging behavior."""

import argparse
import json
from pathlib import Path

import pytest

from scripts import release
from scripts.check_release import verify_files


@pytest.mark.parametrize("value", ["../escape", "latest", "1.2.3;whoami", "-1.2.3", "1.0"])
def test_release_version_rejects_unsafe_paths(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        release.version(value)


def test_release_checksums_reject_tampered_file(tmp_path: Path) -> None:
    payload = tmp_path / "images.tar"
    payload.write_bytes(b"original")
    (tmp_path / "SHA256SUMS").write_text(f"{release.sha256(payload)}  images.tar\n")
    verify_files(tmp_path)
    payload.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        verify_files(tmp_path)


def test_release_checksums_reject_path_escape(tmp_path: Path) -> None:
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  ../outside\n")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        verify_files(tmp_path)


def test_existing_release_is_never_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(release, "ROOT", tmp_path)
    folder = tmp_path / "dist/godfather-1.0.0-linux-amd64"
    folder.mkdir(parents=True)
    marker = folder / "operator-data"
    marker.write_text("preserve")
    with pytest.raises(RuntimeError, match="already exists"):
        release.build("1.0.0")
    assert marker.read_text() == "preserve"


def test_bundle_allowlist_excludes_operator_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(release, "ROOT", tmp_path)
    source = tmp_path / "infrastructure/release"
    for name in (
        "compose.production.yaml",
        "Caddyfile",
        "production.env.example",
        "scripts/common.sh",
        "scripts/backup.sh",
        "scripts/install.sh",
        "scripts/setup.sh",
    ):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"template\r\n")
    (source / ".env").write_text("operator-secret")
    (source / "credentials.json").write_text("operator-secret")
    (source / "production.env").write_text("operator-secret")
    pins = {
        key: f"example/{key}@sha256:" + "a" * 64
        for key in ("python", "uv", "node", *release.UPSTREAM)
    }
    (source / "images.lock.json").write_text(json.dumps(pins))
    (tmp_path / "infrastructure/ollama-runtimes.json").write_text('{"artifacts": []}')
    docs = tmp_path / "docs/operations"
    docs.mkdir(parents=True)
    for name in (
        "production-release.md",
        "founder-bootstrap.md",
        "first-deployment.md",
        "worker-distribution.md",
    ):
        (docs / name).write_text("documentation")
    output = tmp_path / "output"
    output.mkdir()
    release.assemble(output, "1.0.0", {}, "a" * 40)
    assert not (output / ".env").exists()
    assert not (output / "credentials.json").exists()
    assert not (output / "production.env").exists()
    assert (output / "scripts/install.sh").read_bytes() == b"template\n"
    assert (output / "FOUNDER.md").read_text() == "documentation"
    assert (output / "DEPLOYMENT.md").read_text() == "documentation"
    verify_files(output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["source_dirty"] is False
    assert manifest["source_revision"] == "a" * 40
    assert manifest["image_sources"] == pins


def test_dirty_source_refused_before_creating_output_or_running_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(release, "ROOT", tmp_path)

    def git_only(*args: str, **kwargs: object) -> str:
        assert args[0] == "git"
        assert "status" in args
        return "?? private-uncommitted-file"

    monkeypatch.setattr(release, "run", git_only)
    with pytest.raises(RuntimeError, match="source is dirty"):
        release.build("1.0.0")
    assert not (tmp_path / "dist").exists()


def test_image_sources_refuse_mutable_tags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(release, "ROOT", tmp_path)
    folder = tmp_path / "infrastructure/release"
    folder.mkdir(parents=True)
    sources = {key: f"example/{key}:latest" for key in ("python", "uv", "node", *release.UPSTREAM)}
    (folder / "images.lock.json").write_text(json.dumps(sources))
    with pytest.raises(RuntimeError, match="immutable SHA-256 pins"):
        release.image_sources()
