"""Explicit owner-approved portable Ollama installation; no services or root access."""

import asyncio
import hashlib
import os
import re
import shutil
import ssl
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

import certifi
from godfather_model_gateway import GatewayError, ProviderConfig
from godfather_model_gateway.providers import OllamaProvider

from godfather_worker.updates import native_target, read_manifest

_servers: dict[str, subprocess.Popen[bytes]] = {}


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> Request | None:
        parsed = urlsplit(newurl)
        if (
            parsed.scheme != "https"
            or parsed.hostname
            not in (
                "github.com",
                "release-assets.githubusercontent.com",
                "objects.githubusercontent.com",
            )
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Untrusted runtime download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


def extract_runtime(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    limit = 8 * 1024**3
    total = 0
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                total += member.file_size
                target = destination / member.filename
                if (
                    total > limit
                    or not target.resolve().is_relative_to(destination.resolve())
                    or stat.S_ISLNK(member.external_attr >> 16)
                ):
                    raise ValueError("Unsafe runtime archive")
            zipped.extractall(destination)
    else:
        with tarfile.open(archive) as packed:
            members = packed.getmembers()
            for tar_member in members:
                total += tar_member.size
                if total > limit or not (
                    tar_member.isfile()
                    or tar_member.isdir()
                    or tar_member.issym()
                    or tar_member.islnk()
                ):
                    raise ValueError("Unsafe runtime archive")
                # Official macOS packages contain relative dylib links. The data
                # filter rejects absolute/outside links and special device files.
                tarfile.data_filter(tar_member, str(destination))
            packed.extractall(destination, members=members, filter="data")
    executable = next(
        (
            p
            for p in (
                destination / "ollama.exe",
                destination / "ollama",
                destination / "bin/ollama",
            )
            if p.is_file()
        ),
        None,
    )
    if executable is None:
        raise ValueError("Runtime archive does not contain Ollama")
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def install_runtime(origin: str, folder: Path) -> Path:
    target = native_target()
    catalog = read_manifest(origin, "ollama.json")
    entry = next(
        (i for i in catalog["artifacts"] if isinstance(i, dict) and i.get("target") == target), None
    )
    if entry is None:
        raise ValueError("No approved Ollama runtime is published for this platform")
    url, digest = entry.get("url", ""), entry.get("sha256", "")
    if not isinstance(url, str) or not isinstance(digest, str):
        raise ValueError("Invalid runtime download metadata")
    if not re.fullmatch(
        r"https://github\.com/ollama/ollama/releases/download/v[0-9.]+/(?:ollama-(?:windows-(?:amd64|arm64)\.zip|darwin\.tgz|linux-(?:amd64|arm64)\.tar\.zst))",
        url,
    ) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid approved runtime artifact")
    filenames = {
        "windows-x64": "ollama-windows-amd64.zip",
        "windows-arm64": "ollama-windows-arm64.zip",
        "macos-x64": "ollama-darwin.tgz",
        "macos-arm64": "ollama-darwin.tgz",
        "linux-x64": "ollama-linux-amd64.tar.zst",
        "linux-arm64": "ollama-linux-arm64.tar.zst",
    }
    if url.rsplit("/", 1)[1] != filenames.get(target):
        raise ValueError("Runtime artifact does not match this platform")
    if target.startswith("linux"):
        # The current official Linux archive uses zstd. Core on older Python remains
        # usable; provisioning requires Python 3.14 or the platform's manual install.
        import sys

        if sys.version_info < (3, 14):
            raise ValueError(
                "Portable Linux runtime setup requires Python 3.14; "
                "install Ollama locally on older Python"
            )
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), OfficialRedirect())
    runtime = folder / "local-runtime"
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    with TemporaryDirectory(prefix=".ollama-", dir=runtime) as temporary:
        staging = Path(temporary)
        archive = staging / url.rsplit("/", 1)[1]
        checksum = hashlib.sha256()
        count = 0
        with opener.open(Request(url), timeout=60) as response, archive.open("wb") as output:
            while chunk := response.read(1024**2):
                count += len(chunk)
                if count > 2 * 1024**3:
                    raise ValueError("Runtime download exceeds size limit")
                checksum.update(chunk)
                output.write(chunk)
        if checksum.hexdigest() != digest:
            raise ValueError("Ollama checksum mismatch. Nothing was installed.")
        payload = staging / "payload"
        try:
            executable = extract_runtime(archive, payload)
        except (tarfile.TarError, zipfile.BadZipFile) as error:
            raise ValueError("The approved runtime archive could not be read") from error
        destination = runtime / digest
        if not destination.exists():
            payload.rename(destination)
        relative = executable.relative_to(payload)
        (runtime / "current.txt").write_text(str(Path(digest) / relative), encoding="utf-8")
        return Path(destination) / relative


def managed_executable(folder: Path) -> Path | None:
    try:
        base = folder / "local-runtime"
        executable = base / (base / "current.txt").read_text(encoding="utf-8")
        if executable.resolve().is_relative_to(base.resolve()) and executable.is_file():
            return executable
    except OSError:
        pass
    return None


async def ready(config: ProviderConfig) -> bool:
    provider = OllamaProvider(config.model_copy(update={"timeout_seconds": 3}))
    try:
        await provider.discover()
        return True
    except (GatewayError, OSError, TimeoutError):
        return False
    finally:
        await provider.close()


async def ensure_runtime(
    origin: str, folder: Path, config: ProviderConfig, allow_install: bool
) -> None:
    if await ready(config):
        return
    if config.id != "local-ollama" or config.url.rstrip("/") != "http://127.0.0.1:11434":
        raise ValueError("Automatic runtime setup requires the standard local Ollama connection")
    executable = managed_executable(folder)
    if executable is None:
        existing = shutil.which("ollama")
        executable = Path(existing) if existing else None
    if executable is None:
        if not allow_install:
            raise ValueError(
                "Ollama is unavailable. Approve local runtime setup in Consigliere first."
            )
        executable = await asyncio.to_thread(install_runtime, origin, folder)
    # Start only for the fixed local desktop provider; never expose an inference port.
    key = str(folder.resolve())
    process = _servers.get(key)
    if process is None or process.poll() is not None:
        _servers[key] = subprocess.Popen(
            [str(executable), "serve"],
            env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    for _ in range(60):
        if await ready(config):
            return
        await asyncio.sleep(0.5)
    raise ValueError("Ollama did not become ready. Check local runtime permissions and resources.")
