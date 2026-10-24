"""Explicit, read-only local model search. Weight files are never opened or executed."""

import asyncio
import json
import os
import platform
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from godfather_contracts import ModelInventory
from godfather_model_gateway import GatewayError, ProviderConfig
from godfather_model_gateway.providers import HTTPProvider

MODEL_LIMIT = 128
FILE_LIMIT = 100_000
SCAN_SECONDS = 60
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "blobs", ".locks"}
WEIGHTS = {
    ".gguf",
    ".ggml",
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".onnx",
    ".h5",
    ".hdf5",
    ".tflite",
    ".keras",
    ".mlmodel",
}


@dataclass(frozen=True)
class FoundModel:
    name: str
    source: str
    location: str
    served: bool = False
    gguf_path: str | None = None


@dataclass
class ScanResult:
    models: list[FoundModel] = field(default_factory=list)
    providers: list[ProviderConfig] = field(default_factory=list)
    omitted: int = 0
    unreadable: int = 0
    incomplete: bool = False
    cancelled: bool = False


def default_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(home / ".cache")))
    hf = Path(os.environ.get("HF_HOME", str(cache / "huggingface")))
    roots = [
        home / ".ollama/models",
        home / ".lmstudio/models",
        home / ".cache/lm-studio/models",
        hf / "hub",
        home / ".local/share/nomic.ai/GPT4All",
        home / "Library/Application Support/nomic.ai/GPT4All",
        home / "jan/models",
        home / ".jan/models",
        home / "Models",
        home / "AI",
        home / "Downloads",
        home / "ComfyUI/models",
        home / "Documents/ComfyUI/models",
        home / "stable-diffusion-webui/models",
        home / "Documents/LM Studio/Models",
        cache / "whisper",
        Path(os.environ.get("TORCH_HOME", str(cache / "torch"))) / "hub/checkpoints",
    ]
    if platform.system() == "Linux":
        roots.extend(
            [
                Path("/usr/share/ollama/.ollama/models"),
                Path("/var/lib/ollama/.ollama/models"),
                Path("/opt/ComfyUI/models"),
                Path("/opt/stable-diffusion-webui/models"),
            ]
        )
    if local := os.environ.get("LOCALAPPDATA"):
        roots.append(Path(local) / "nomic.ai/GPT4All")
    for name in ("OLLAMA_MODELS", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE"):
        if value := os.environ.get(name):
            roots.insert(0, Path(value).expanduser())
    if jan := os.environ.get("JAN_DATA_FOLDER"):
        roots.append(Path(jan) / "models")
    # Common dedicated libraries on mounted, local fixed disks. No network volumes.
    import psutil

    try:
        for disk in psutil.disk_partitions():
            if (
                disk.fstype.lower() not in {"nfs", "nfs4", "cifs", "smbfs"}
                and "remote" not in disk.opts
            ):
                roots.extend(
                    Path(disk.mountpoint) / name
                    for name in (
                        "Models",
                        "AI",
                        "ComfyUI/models",
                        "stable-diffusion-webui/models",
                    )
                )
    except (OSError, psutil.Error):
        pass
    return list(dict.fromkeys(roots))


def local_servers() -> list[ProviderConfig]:
    return [
        ProviderConfig(id="local-ollama", provider="ollama"),
        *[
            ProviderConfig(
                id=f"local-server-{port}",
                provider="openai_compatible",
                url=f"http://127.0.0.1:{port}/v1",
            )
            for port in (1234, 4891, 1337, 8080, 8000, 5001)
        ],
    ]


async def server_models(config: ProviderConfig) -> list[str]:
    if (
        config.provider not in ("ollama", "openai_compatible")
        or urlsplit(config.url).hostname not in ("127.0.0.1", "localhost", "::1")
        or config.api_key_env
        or config.connection_id
    ):
        raise ValueError("Model scans use only unauthenticated loopback model metadata")
    provider = HTTPProvider(config.model_copy(update={"timeout_seconds": 2}))
    try:
        async with asyncio.timeout(3):
            data = await provider.request(
                "GET", "api/tags" if config.provider == "ollama" else "models"
            )
        rows = data.get("models" if config.provider == "ollama" else "data", [])
        if not isinstance(rows, list):
            return []
        result = []
        for row in rows:
            name = (
                row.get("name" if config.provider == "ollama" else "id")
                if isinstance(row, dict)
                else None
            )
            try:
                name = ModelInventory(runtime=config.provider, identifier=name).identifier
            except ValueError:
                continue
            if name not in result:
                result.append(name)
        return result
    except (GatewayError, TimeoutError):
        return []
    finally:
        await provider.close()


async def probe_servers(configs: list[ProviderConfig]) -> list[list[str]]:
    return list(await asyncio.gather(*(server_models(c) for c in configs)))


def file_model(path: Path) -> tuple[str, Path] | None:
    """Group sharded checkpoints and HF/MLX/Diffusers snapshots, not their tensors."""
    suffix, name = path.suffix.lower(), path.name.lower()
    if suffix not in WEIGHTS and not (
        suffix == ".bin" and name.startswith(("pytorch_model", "model", "adapter_model", "ggml"))
    ):
        return None
    if path.stat().st_size == 0:
        return None
    parts = path.parts
    if "snapshots" in parts:
        i = parts.index("snapshots")
        if i > 0 and len(parts) > i + 2:
            snapshot = Path(*parts[: i + 2])
            repo = parts[i - 1].removeprefix("models--").replace("--", "/")
            # GGUF quantizations are independent choices, even inside one HF snapshot.
            if suffix not in {".gguf", ".ggml"}:
                return f"{repo} ({parts[i + 1][:8]})", snapshot
    parent = path.parent
    if name.startswith(("model", "pytorch_model", "adapter_model", "diffusion_pytorch_model")) and (
        (parent / "config.json").is_file() or (parent / "model_index.json").is_file()
    ):
        return parent.name, parent
    grouped = re.sub(r"[-_]\d{5}-of-\d{5}", "", path.name)
    return grouped, parent / grouped


def ollama_manifest(path: Path) -> tuple[str, Path] | None:
    if "manifests" not in path.parts or path.stat().st_size > 1024**2:
        return None
    i = path.parts.index("manifests")
    components = path.parts[i + 2 :]
    if len(components) < 3:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    layers = data.get("layers", [])
    if not isinstance(layers, list) or not layers:
        return None
    store = Path(*path.parts[:i])
    # Incomplete downloads and stale manifests are not installed models.
    for layer in layers:
        digest = layer.get("digest", "") if isinstance(layer, dict) else ""
        if (
            not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
            or not (store / "blobs" / digest.replace(":", "-")).is_file()
        ):
            return None
    namespace, *model, tag = components
    prefix = "" if namespace == "library" else namespace + "/"
    return prefix + "/".join(model) + ":" + tag, path


def ollama_weight_path(path: Path) -> str | None:
    """A validated manifest's model layer, without opening the weight file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    root = Path(*path.parts[: path.parts.index("manifests")])
    for layer in data.get("layers", []):
        if layer.get("mediaType") == "application/vnd.ollama.image.model":
            digest = layer.get("digest", "")
            if re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                return str(root / "blobs" / digest.replace(":", "-"))
    return None


def scan(
    roots: list[Path],
    configs: list[ProviderConfig] | None = None,
    cancel: threading.Event | None = None,
    progress: Callable[[str], None] | None = None,
) -> ScanResult:
    result = ScanResult()
    cancel = cancel or threading.Event()
    progress = progress or (lambda _: None)
    seen: set[tuple[str, str]] = set()

    def add(model: FoundModel, key: tuple[str, str]) -> None:
        if key in seen:
            if model.gguf_path and key[0] == "local-ollama":
                for i, found in enumerate(result.models):
                    if found.source == "ollama" and found.name == model.name:
                        result.models[i] = replace(found, gguf_path=model.gguf_path)
                        break
            return
        seen.add(key)
        if len(result.models) < MODEL_LIMIT:
            result.models.append(model)
        else:
            result.omitted += 1

    progress("Checking running local model servers…")
    configs = configs if configs is not None else local_servers()
    if cancel.is_set():
        result.cancelled = result.incomplete = True
        return result
    if len(configs) > 8:
        raise ValueError("The local provider limit is eight")
    for config, names in zip(configs, asyncio.run(probe_servers(configs)), strict=True):
        selected = []
        for name in names:
            before = len(result.models)
            add(FoundModel(name, config.provider, config.url, True), (config.id, name))
            if len(result.models) > before:
                selected.append(name)
        if selected:
            result.providers.append(config.model_copy(update={"discovery_models": selected}))
    if cancel.is_set():
        result.cancelled = result.incomplete = True
        return result
    started, visited = monotonic(), 0
    directories: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        progress(f"Scanning {root.name or root.anchor}…")
        pending = [root]
        while pending:
            if cancel.is_set() or visited >= FILE_LIMIT or monotonic() - started >= SCAN_SECONDS:
                result.cancelled, result.incomplete = cancel.is_set(), True
                return result
            directory = pending.pop()
            try:
                resolved = directory.resolve()
                if resolved in directories:
                    continue
                directories.add(resolved)
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited += 1
                        if (
                            visited >= FILE_LIMIT
                            or cancel.is_set()
                            or monotonic() - started >= SCAN_SECONDS
                        ):
                            result.cancelled, result.incomplete = cancel.is_set(), True
                            return result
                        path = Path(entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in SKIP and not path.is_junction():
                                if path.suffix.lower() in {".mlpackage", ".mlmodelc"}:
                                    add(
                                        FoundModel(path.name, "Core ML bundle", str(path)),
                                        ("file", str(path.resolve())),
                                    )
                                else:
                                    pending.append(path)
                            continue
                        if not entry.is_file():
                            continue
                        try:
                            manifest = ollama_manifest(path)
                            found = manifest or file_model(path)
                            if found:
                                name, location = found
                                source = "Ollama library" if manifest else "Model files"
                                # A served Ollama model and its on-disk manifest are one result.
                                key = (
                                    ("local-ollama", name)
                                    if manifest
                                    else ("file", str(location.resolve()))
                                )
                                display = location if location.exists() else location.parent
                                add(
                                    FoundModel(
                                        name,
                                        source,
                                        str(display),
                                        gguf_path=ollama_weight_path(path) if manifest else None,
                                    ),
                                    key,
                                )
                        except (OSError, ValueError, TypeError, AttributeError):
                            result.unreadable += 1
            except OSError:
                result.unreadable += 1
    return result
