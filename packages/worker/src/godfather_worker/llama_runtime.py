"""Pinned, owner-approved portable llama.cpp. No services, drivers or model downloads."""

import hashlib
import json
import os
import re
import ssl
import subprocess
import tarfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

import certifi
from godfather_contracts.shared_engine import ENGINE_VERSION, EngineDevice

from godfather_worker.app_installation import extract_zip
from godfather_worker.updates import native_target

Progress = Callable[[str, int, int | None], None]


def catalog() -> dict[str, Any]:
    return dict(
        json.loads(
            (Path(__file__).parent / "assets/llama-runtime.json").read_text(encoding="utf-8")
        )
    )


def variants(target: str | None = None) -> list[str]:
    prefix = (target or native_target()) + "/"
    return [key.split("/")[1] for key in catalog()["artifacts"] if key.startswith(prefix)]


def runtime_folder(folder: Path, backend: str, target: str | None = None) -> Path:
    target = target or native_target()
    if target + "/" + backend not in catalog()["artifacts"]:
        raise ValueError("No approved llama.cpp build is available for this platform/backend")
    return folder / "shared-engine/runtimes" / f"{ENGINE_VERSION}-{target}-{backend}"


def environment(root: Path) -> dict[str, str]:
    # Do not inherit engine flags, provider tokens, model URLs or automatic tool settings.
    keep = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
    }
    values = {k: v for k, v in os.environ.items() if k.upper() in keep}
    values.update(
        {"HF_HUB_OFFLINE": "1", "LLAMA_ARG_OFFLINE": "1", "LLAMA_CACHE": str(root / "cache")}
    )
    return values


@dataclass(frozen=True)
class Runtime:
    root: Path
    server: Path
    rpc: Path


def binaries(root: Path) -> Runtime:
    def find(names: tuple[str, ...]) -> Path:
        for name in names:
            for path in root.rglob(name):
                if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                    return path.resolve()
        raise ValueError("The approved runtime archive is missing the server or RPC executable")

    return Runtime(
        root,
        find(("llama-server.exe", "llama-server")),
        find(("rpc-server.exe", "rpc-server", "ggml-rpc-server.exe", "ggml-rpc-server")),
    )


def existing(folder: Path, backend: str, target: str | None = None) -> Runtime | None:
    root = runtime_folder(folder, backend, target)
    if not root.exists():
        return None
    expected = catalog()["artifacts"][(target or native_target()) + "/" + backend][1]
    try:
        manifest = json.loads((root / "verified.json").read_text(encoding="utf-8"))
        if manifest["archive_sha256"] != expected or not isinstance(manifest["files"], dict):
            raise ValueError("Runtime identity changed")
        for name, checksum in manifest["files"].items():
            path = root / name
            if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError("Runtime file is unavailable")
            with path.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != checksum:
                    raise ValueError("Runtime checksum changed")
        runtime = binaries(root)
        for executable in (runtime.server, runtime.rpc):
            if executable.relative_to(root.resolve()).as_posix() not in manifest["files"]:
                raise ValueError("Runtime executable was not verified")
        return runtime
    except (OSError, KeyError, TypeError, ValueError):
        raise ValueError(
            "The local llama.cpp installation failed verification. Choose a "
            "clean worker runtime folder or repair it before starting."
        ) from None


class ReleaseRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> Request | None:
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in (
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        ):
            raise ValueError("Runtime download redirected outside the approved release hosts")
        return Request(newurl, headers={"User-Agent": "Godfather-Consigliere"})


def install(
    folder: Path,
    backend: str,
    allow_download: bool,
    cancel: threading.Event | None = None,
    progress: Progress | None = None,
) -> Runtime:
    found = existing(folder, backend)
    if found:
        return found
    if not allow_download:
        raise ValueError("Allow the verified llama.cpp download in Shared Inference first")
    cancel = cancel or threading.Event()
    progress = progress or (lambda stage, completed, total: None)
    name, expected = catalog()["artifacts"][native_target() + "/" + backend]
    destination = runtime_folder(folder, backend)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    context = ssl.create_default_context(cafile=certifi.where())
    opener = build_opener(ProxyHandler({}), ReleaseRedirect(), HTTPSHandler(context=context))
    with TemporaryDirectory(prefix=".llama-download-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        archive = staging / name
        digest, count = hashlib.sha256(), 0
        url = f"https://github.com/ggml-org/llama.cpp/releases/download/{ENGINE_VERSION}/{name}"
        progress("Downloading verified llama.cpp", 0, None)
        with opener.open(Request(url), timeout=30) as response, archive.open("wb") as output:
            raw_total = response.headers.get("Content-Length", "")
            total = int(raw_total) if raw_total.isdigit() else None
            while chunk := response.read(1024**2):
                if cancel.is_set():
                    raise ValueError("Runtime setup cancelled")
                count += len(chunk)
                if count > 512 * 1024**2:
                    raise ValueError("Runtime download exceeds its size limit")
                output.write(chunk)
                digest.update(chunk)
                progress("Downloading verified llama.cpp", count, total)
        if digest.hexdigest() != expected:
            raise ValueError("llama.cpp checksum mismatch; nothing was installed")
        progress("Verifying and extracting llama.cpp", count, count)
        content = staging / "runtime"
        content.mkdir(mode=0o700)
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as package:
                extract_zip(package, content)
        else:
            with tarfile.open(archive, "r:gz") as package:
                members = package.getmembers()
                if len(members) > 10_000 or sum(m.size for m in members) > 2 * 1024**3:
                    raise ValueError("Runtime archive exceeds extraction limits")
                package.extractall(content, filter="data")
        runtime = binaries(content)
        for path in (runtime.server, runtime.rpc):
            path.chmod(0o700)
        files = {}
        for path in content.rglob("*"):
            if path.is_file():
                with path.open("rb") as source:
                    files[path.relative_to(content).as_posix()] = hashlib.file_digest(
                        source, "sha256"
                    ).hexdigest()
        (content / "verified.json").write_text(
            json.dumps({"archive_sha256": expected, "files": files}), encoding="utf-8"
        )
        if cancel.is_set():
            raise ValueError("Runtime setup cancelled")
        content.rename(destination)
    progress("llama.cpp is installed", 1, 1)
    return binaries(destination)


def run_probe(runtime: Runtime, arguments: list[str]) -> str:
    result = subprocess.run(
        [str(runtime.server), *arguments],
        cwd=runtime.server.parent,
        env=environment(runtime.root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    )
    if result.returncode:
        raise ValueError(
            "llama.cpp could not inspect devices. Check this computer's "
            "runtime/backend and installed driver."
        )
    return (result.stdout + "\n" + result.stderr)[:262144]


def devices(runtime: Runtime, rpc: list[str] | None = None) -> list[EngineDevice]:
    args = ["--list-devices"]
    if rpc:
        args += ["--rpc", ",".join(rpc)]
    output = run_probe(runtime, args)
    result = []
    if "Available devices:" not in output:
        raise ValueError("The runtime did not return a device inventory")
    output = output.split("Available devices:", 1)[1]
    for line in output.splitlines():
        match = re.match(r"\s*([A-Za-z][^\s]*):\s+(.+?)(?:\s+\((\d+)\s+MiB.*\))?\s*$", line)
        if not match or match[1] in ("Available", "Devices"):
            continue
        identity, name = match[1], match[2]
        if not re.fullmatch(r"(?:CUDA|Vulkan|Metal|ROCm|HIP)\d*", identity, re.IGNORECASE):
            continue
        lowered = identity.lower()
        backend = (
            "cuda"
            if lowered.startswith("cuda")
            else "vulkan"
            if lowered.startswith("vulkan")
            else "metal"
            if lowered.startswith("metal")
            else "rocm"
            if lowered.startswith(("rocm", "hip"))
            else "unknown"
        )
        result.append(
            EngineDevice(
                id=identity,
                name=name[:200],
                backend=backend,
                memory_bytes=int(match[3]) * 1024**2 if match[3] else None,
            )
        )
    return [*result, EngineDevice(id="CPU", name="CPU", backend="cpu")]


def gguf(path: Path) -> Path:
    if not path.is_file():
        raise ValueError("The installed model file is unavailable")
    with path.open("rb") as source:
        if source.read(4) != b"GGUF":
            raise ValueError("Choose an installed GGUF model supported by llama.cpp")
    return path.resolve()
