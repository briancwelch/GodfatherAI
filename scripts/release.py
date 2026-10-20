"""Build a local, source-free Linux AMD64 coordinator release. Never deploys."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.dev import ROOT

UPSTREAM = ("postgres", "redis", "caddy")


def version(value: str) -> str:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?", value):
        raise argparse.ArgumentTypeError("Use a version such as 0.1.0-rc.1")
    return value


def run(*args: str, capture: bool = False) -> str:
    executable = shutil.which(args[0])
    if executable is None:
        raise RuntimeError(f"Missing build prerequisite: {args[0]}")
    result = subprocess.run(
        [executable, *args[1:]],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_revision() -> str:
    """Refuse dirty inputs before Docker work, and detect changes during a build."""
    command = ("git", "-c", f"safe.directory={ROOT.as_posix()}")
    if run(*command, "status", "--porcelain", "--untracked-files=all", capture=True):
        raise RuntimeError("Release source is dirty; review and commit changes before building")
    revision = run(*command, "rev-parse", "HEAD", capture=True)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Release requires an exact committed Git revision")
    return revision


def image_sources() -> dict[str, str]:
    sources: dict[str, str] = json.loads(
        (ROOT / "infrastructure/release/images.lock.json").read_text(encoding="utf-8")
    )
    if set(sources) != {"python", "uv", "node", *UPSTREAM} or any(
        not isinstance(value, str) or not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", value)
        for value in sources.values()
    ):
        raise RuntimeError("All production image inputs must have immutable SHA-256 pins")
    return sources


def image_info(tag: str) -> dict[str, Any]:
    info: dict[str, Any] = json.loads(run("docker", "image", "inspect", tag, capture=True))[0]
    if (info["Os"], info["Architecture"]) != ("linux", "amd64"):
        raise RuntimeError(f"Incorrect target architecture: {tag}")
    return {
        "tag": tag,
        "id": info["Id"],
        "size_bytes": info["Size"],
        "platform": "linux/amd64",
        "repo_digests": info.get("RepoDigests", []),
    }


def assemble(
    folder: Path,
    release: str,
    images: dict[str, dict[str, Any]],
    revision: str,
) -> None:
    """Allowlist package contents; never copy the checkout or operator environment."""
    source = ROOT / "infrastructure/release"
    for relative in (
        "compose.production.yaml",
        "Caddyfile",
        "production.env.example",
        "images.lock.json",
        "scripts/common.sh",
        "scripts/backup.sh",
        "scripts/install.sh",
    ):
        path = source / relative
        destination = folder / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Normalize shell scripts/configuration for Windows-built releases.
        destination.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    for name, target in (
        ("production-release.md", "INSTALL.md"),
        ("worker-distribution.md", "WORKERS.md"),
    ):
        shutil.copyfile(ROOT / "docs/operations" / name, folder / target)
    (folder / "release.env").write_text(
        "".join(f"{name.upper()}_IMAGE={info['tag']}\n" for name, info in images.items()),
        encoding="utf-8",
        newline="\n",
    )
    (folder / "image-ids.txt").write_text(
        "".join(f"{info['tag']} {info['id']}\n" for info in images.values()),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "release": release,
        "created_utc": datetime.now(UTC).isoformat(),
        "source_revision": revision,
        "source_dirty": False,
        "image_sources": image_sources(),
        "platform": "linux/amd64",
        "acceptance": "local release candidate; real Google and remote Phase 10 gates pending",
        "images": images,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    (folder / "SHA256SUMS").write_text(
        "".join(f"{sha256(p)}  {p.relative_to(folder).as_posix()}\n" for p in files),
        encoding="utf-8",
        newline="\n",
    )


def build(release: str) -> Path:
    folder = ROOT / "dist" / f"godfather-{release}-linux-amd64"
    archive = Path(str(folder) + ".tar.gz")
    if folder.exists() or archive.exists():
        raise RuntimeError("Release output already exists; choose a new version (never overwrite)")
    revision = source_revision()
    sources = image_sources()
    folder.mkdir(parents=True)
    images: dict[str, dict[str, Any]] = {}
    for name in ("api", "dashboard"):
        tag = f"godfather/{name}:{release}"
        command = [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "--load",
            "--tag",
            tag,
            "--file",
            f"infrastructure/docker/{name}.Dockerfile",
        ]
        if name == "api":
            command += [
                "--target",
                "production",
                "--build-arg",
                f"PYTHON_IMAGE={sources['python']}",
                "--build-arg",
                f"UV_IMAGE={sources['uv']}",
            ]
        else:
            command += ["--build-arg", f"NODE_IMAGE={sources['node']}"]
        run(*command, ".")
        images[name] = image_info(tag)
    for name in UPSTREAM:
        upstream = sources[name]
        run("docker", "pull", "--platform", "linux/amd64", upstream)
        info = image_info(upstream)
        tag = f"godfather/{name}:{release}"
        run("docker", "tag", upstream, tag)
        images[name] = {
            **image_info(tag),
            "upstream": upstream,
            "upstream_repo_digests": info["repo_digests"],
        }
    run(
        "docker",
        "save",
        "--output",
        str(folder / "images.tar"),
        *(str(info["tag"]) for info in images.values()),
    )
    if source_revision() != revision:
        raise RuntimeError("Git revision changed during build; release refused")
    assemble(folder, release, images, revision)
    if source_revision() != revision:
        raise RuntimeError("Git revision changed during assembly; release refused")
    with tarfile.open(archive, "w:gz", compresslevel=6) as bundle:
        bundle.add(folder, arcname=folder.name, filter=tar_permissions)
    Path(str(archive) + ".sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Release candidate: {archive}")
    return archive


def tar_permissions(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mode = 0o755 if info.isdir() or info.name.endswith(".sh") else 0o644
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=version)
    args = parser.parse_args()
    build(args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
