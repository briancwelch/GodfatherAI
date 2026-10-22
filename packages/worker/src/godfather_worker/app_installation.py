"""Replace only verified application directories, keeping owner data separate."""

import json
import shutil
import stat
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


def extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    total = 0
    for member in archive.infolist():
        total += member.file_size
        if (
            total > 8 * 1024**3
            or not (destination / member.filename).resolve().is_relative_to(destination.resolve())
            or stat.S_ISLNK(member.external_attr >> 16)
        ):
            raise ValueError("Unsafe application archive")
    archive.extractall(destination)


def contained_directory(path: Path, parent: Path) -> None:
    if (
        path.is_symlink()
        or not path.resolve().is_relative_to(parent.resolve())
        or path.resolve() == parent.resolve()
    ):
        raise OSError("Application path escapes its installation folder")
    if any(p.is_symlink() or p.is_junction() for p in [path, *path.rglob("*")]):
        raise OSError("Application directory contains an unexpected link")


def replace_payload(payload: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    contained_directory(destination, destination.parent)
    with TemporaryDirectory(prefix=".consigliere-install-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "payload"
        backup = Path(temporary) / "previous"
        shutil.copytree(payload, staged)
        if destination.exists():
            destination.rename(backup)
        try:
            staged.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise


def legacy_windows_versions(base: Path) -> list[Path]:
    versions = base / "versions"
    if not versions.exists():
        return []
    contained_directory(versions, base)
    result = []
    for path in versions.iterdir():
        contained_directory(path, versions)
        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            if (
                manifest.get("version") != path.name
                or manifest.get("target") != "windows-x64"
                or not (path / "godfather-worker.exe").is_file()
            ):
                raise ValueError("Not an installed worker")
        except (OSError, ValueError):
            raise OSError(
                "Unrecognized legacy application folder; review it before upgrading"
            ) from None
        result.append(path)
    return result
