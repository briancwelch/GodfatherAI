"""Owner-controlled, HTTPS/hash verified native worker update handoff."""

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.request import Request

import psutil

from godfather_worker.client import WorkerClient

VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def version_key(value: str) -> tuple[Any, ...]:
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError("Invalid release version")
    suffix = match[4]
    return (
        *(int(match[i]) for i in (1, 2, 3)),
        suffix is None,
        tuple((0, int(v)) if v.isdigit() else (1, v) for v in suffix.split(".")) if suffix else (),
    )


def native_target() -> str:
    system = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[platform.system()]
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}
    return system + "-" + arch[platform.machine().lower()]


def read_manifest(origin: str, name: str = "manifest.json") -> dict[str, Any]:
    if name not in ("manifest.json", "ollama.json"):
        raise ValueError("Unknown download catalog")
    client = WorkerClient(origin, "")
    with client.opener.open(Request(client.url + "/downloads/" + name), timeout=15) as response:
        raw = response.read(1024**2 + 1)
    if len(raw) > 1024**2:
        raise ValueError("Download catalog exceeds size limit")
    result = json.loads(raw)
    if not isinstance(result, dict) or not isinstance(result.get("artifacts"), list):
        raise ValueError("Invalid download catalog")
    return result


def available_update(origin: str, current: str, target: str | None = None) -> dict[str, str] | None:
    target = target or native_target()
    suffixes = {
        "windows-x64": "windows-x64-setup.exe",
        "macos-arm64": "macos-arm64-installer.dmg",
        "macos-x64": "macos-x64-installer.dmg",
        "linux-x64": "linux-x64.zip",
        "linux-arm64": "linux-arm64.zip",
    }
    if target not in suffixes:
        return None
    candidates = []
    published = False
    for item in read_manifest(origin)["artifacts"]:
        if not isinstance(item, dict):
            continue
        name, digest = item.get("filename", ""), item.get("sha256", "")
        if (
            not isinstance(name, str)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
        ):
            continue
        match = re.fullmatch(
            r"(?:consigliere|godfather-worker)-(.+)-" + re.escape(suffixes[target]), name
        )
        if match and VERSION.fullmatch(match[1]):
            published = True
            if version_key(match[1]) > version_key(current):
                candidates.append({"filename": name, "sha256": digest, "version": match[1]})
    if not published:
        raise ValueError("No compatible worker download is published")
    return max(candidates, key=lambda c: version_key(c["version"])) if candidates else None


def download_update(origin: str, item: dict[str, str], folder: Path) -> Path:
    # Re-read the trusted catalog immediately before handoff; reject stale/replaced builds.
    selected = available_update(origin, "0.0.0")
    if selected != item:
        raise ValueError("The published update changed. Check for updates again.")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = folder / item["filename"]
    partial = destination.with_suffix(destination.suffix + ".partial")
    digest = hashlib.sha256()
    count = 0
    try:
        client = WorkerClient(origin, "")
        with (
            client.opener.open(
                Request(client.url + "/downloads/" + item["filename"]), timeout=60
            ) as response,
            partial.open("wb") as output,
        ):
            while chunk := response.read(1024**2):
                count += len(chunk)
                if count > 2 * 1024**3:
                    raise ValueError("Worker download exceeds size limit")
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != item["sha256"]:
            raise ValueError("Worker checksum mismatch. Nothing was installed.")
        partial.replace(destination)
        return destination
    finally:
        partial.unlink(missing_ok=True)


def launch_update(path: Path, expected_sha256: str) -> None:
    """The existing native installer waits for this process and retains owner data."""
    with path.open("rb") as payload:
        if hashlib.file_digest(payload, "sha256").hexdigest() != expected_sha256:
            raise ValueError("Worker checksum changed before installation")
    args = ["--auto-update", "--wait-pid", str(os.getpid())]
    if platform.system() == "Windows" and path.suffix == ".exe":
        subprocess.Popen(
            [str(path), *args], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    elif platform.system() == "Darwin" and path.suffix == ".dmg":
        import plistlib

        result = subprocess.run(
            ["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(path)],
            capture_output=True,
            check=True,
            timeout=60,
        )
        mounts = plistlib.loads(result.stdout)["system-entities"]
        mounted = next(Path(m["mount-point"]) for m in mounts if "mount-point" in m)
        executable = mounted / "Consigliere.app/Contents/MacOS/Consigliere"
        subprocess.Popen([str(executable), "--install", *args])
    elif platform.system() == "Linux" and path.suffix == ".zip":
        import zipfile

        from godfather_worker.app_installation import extract_zip

        destination = path.parent / (path.stem + "-staged")
        with zipfile.ZipFile(path) as archive:
            extract_zip(archive, destination)
        executable = destination / path.stem / "consigliere"
        executable.chmod(0o700)
        subprocess.Popen(
            [str(executable), "--install-update", str(Path(sys.executable).resolve().parent), *args]
        )
    else:
        raise ValueError("Use your platform's normal worker installation instructions")


def wait_for_previous() -> None:
    if "--wait-pid" in sys.argv:
        pid = int(sys.argv[sys.argv.index("--wait-pid") + 1])
        with suppress(psutil.NoSuchProcess):
            psutil.Process(pid).wait(timeout=120)


def update_failure() -> int:
    """Installer failures must remain visible after the old worker exits."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Update incomplete",
        "The worker update did not finish. Reopen Consigliere and retry. "
        "Your saved connection and projects were retained. "
        "Check application-folder permissions and free storage.",
        parent=root,
    )
    root.destroy()
    return 1
