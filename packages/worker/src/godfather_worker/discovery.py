"""Best-effort read-only discovery adapters. No driver installs or inference probes."""

import csv
import json
import os
import platform
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Literal

import psutil
from godfather_contracts import GPU, Advertisement, ModelInventory, Resources


def run(*command: str) -> str:
    """Bounded, shell-free, local-only subprocess. Unsupported tools are normal."""
    executable = shutil.which(command[0])
    if executable is None:
        return ""
    try:
        result = subprocess.run(
            [executable, *command[1:]],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        return result.stdout[:262144] if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def number(value: object, multiplier: int = 1) -> int | None:
    try:
        return max(0, int(float(str(value)) * multiplier))
    except (ValueError, OverflowError):
        return None


def nvidia_gpus() -> list[GPU]:
    output = run(
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    )
    result = []
    for row in csv.reader(output.splitlines()):
        if len(row) != 4 or not row[0].strip():
            continue
        usage = number(row[3])
        result.append(
            GPU(
                name=row[0].strip()[:100],
                backend="cuda",
                evidence="driver",
                memory_bytes=number(row[1], 1024**2),
                memory_used_bytes=number(row[2], 1024**2),
                utilization_percent=usage if usage is not None and usage <= 100 else None,
            )
        )
    return result


def windows_gpus() -> list[GPU]:
    output = run(
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress",
    )
    try:
        data = json.loads(output)
        rows = data if isinstance(data, list) else [data]
        return [
            GPU(name=str(row["Name"])[:100])
            for row in rows
            if isinstance(row, dict) and row.get("Name")
        ]
    except (ValueError, TypeError):
        return []
    # AdapterRAM is a 32-bit CIM field; never present it as trustworthy modern VRAM.


def metal_reported(value: object) -> bool:
    text = str(value or "").lower()
    return (
        "unsupported" not in text
        and "not supported" not in text
        and (text in ("supported", "yes") or "metal" in text)
    )


def macos_gpus() -> list[GPU]:
    try:
        data = json.loads(run("system_profiler", "SPDisplaysDataType", "-json"))
        rows = data.get("SPDisplaysDataType", []) if isinstance(data, dict) else []
        return [
            GPU(
                name=str(row.get("sppci_model", "Unknown GPU"))[:100],
                backend="metal" if metal_reported(row.get("spdisplays_metal")) else "unknown",
                unified_memory=(platform.machine().lower() in ("arm64", "aarch64")),
            )
            for row in rows
            if isinstance(row, dict)
        ]
    except (ValueError, TypeError):
        return []


def linux_gpus() -> list[GPU]:
    result = []
    # A working ROCm inventory command is evidence of reported support, not inference validation.
    rocm = "gfx" in run("rocminfo")
    for card in Path("/sys/class/drm").glob("card[0-9]*"):
        if "-" in card.name:
            continue
        device = card / "device"
        try:
            vendor = (device / "vendor").read_text().strip()
            product = (device / "device").read_text().strip()
            if vendor == "0x10de":  # NVIDIA comes from the driver probe, below.
                result.append(GPU(name=f"NVIDIA PCI {product}"))
            else:
                brand = {"0x1002": "AMD", "0x8086": "Intel"}.get(vendor, "PCI")
                gpu = GPU(
                    name=f"{brand} GPU {product}",
                    backend="rocm" if vendor == "0x1002" and rocm else "unknown",
                )
                for filename, field in (
                    ("mem_info_vram_total", "memory_bytes"),
                    ("mem_info_vram_used", "memory_used_bytes"),
                ):
                    with suppress(OSError):
                        setattr(gpu, field, number((device / filename).read_text().strip()))
                result.append(gpu)
        except OSError:
            continue
    return result


def discover_resources() -> tuple[Resources, list[str]]:
    warnings: list[str] = []
    try:
        cpu_count = psutil.cpu_count() or 1
    except (OSError, psutil.Error, NotImplementedError):
        cpu_count = 1
        warnings.append("cpu-count-unavailable")
    resources = Resources(
        source="physical",
        cpu_name=platform.processor()[:200] or "Unknown CPU",
        cpu_count=cpu_count,
    )
    try:
        memory = psutil.virtual_memory()
        resources.ram_bytes, resources.available_ram_bytes = memory.total, memory.available
        # First nonblocking sample has no elapsed interval and is deliberately unknown.
        resources.cpu_percent = psutil.cpu_percent(interval=None) if _primed[0] else None
        if not _primed[0]:
            psutil.cpu_percent(interval=None)
            _primed[0] = True
    except (OSError, psutil.Error, NotImplementedError):
        warnings.append("host-telemetry-unavailable")
    nvidia = nvidia_gpus()
    adapters = {"Windows": windows_gpus, "Darwin": macos_gpus, "Linux": linux_gpus}
    try:
        other = adapters.get(platform.system(), lambda: [])()
    except (OSError, ValueError, TypeError, KeyError):
        other = []
        warnings.append("gpu-discovery-unavailable")
    names = {gpu.name for gpu in nvidia}
    resources.gpus = (
        nvidia
        + [
            gpu
            for gpu in other
            if gpu.name not in names and not (nvidia and "NVIDIA" in gpu.name.upper())
        ]
    )[:32]
    if any(gpu.backend == "unknown" for gpu in resources.gpus):
        warnings.append("gpu-backend-unverified")
    if not resources.gpus:
        warnings.append("no-gpu-detected-or-probe-unavailable")
    return resources, warnings


_primed = [False]


def discover(*, include_models: bool = True) -> Advertisement:
    systems: dict[str, Literal["windows", "macos", "linux"]] = {
        "Windows": "windows",
        "Darwin": "macos",
        "Linux": "linux",
    }
    system = systems.get(platform.system())
    if system is None:
        raise ValueError("Supported worker hosts are Windows, macOS and Linux")
    architecture: Literal["x86_64", "arm64", "x86", "unknown"] = "unknown"
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        architecture = "x86_64"
    elif machine in ("arm64", "aarch64"):
        architecture = "arm64"
    elif machine in ("x86", "i386", "i686"):
        architecture = "x86"
    resources, warnings = discover_resources()
    runtimes = ["python"]
    models = []
    if include_models and shutil.which("ollama"):
        runtimes.append("ollama")
        output = run("ollama", "list")
        if not output:
            warnings.append("ollama-model-inventory-unavailable")
        else:
            for line in output.splitlines()[1:129]:
                columns = line.split()
                if columns:
                    try:
                        models.append(ModelInventory(runtime="ollama", identifier=columns[0]))
                    except ValueError:
                        warnings.append("unsupported-model-identifier")
    return Advertisement(
        os=system,
        os_version=platform.release()[:100] or "unknown",
        architecture=architecture,
        resources=resources,
        runtimes=runtimes,
        installed_models=models,
        toolchains=[tool for tool in ("git", "node", "docker") if shutil.which(tool)],
        # Tool availability never constitutes sandbox or host permission.
        sandbox_modes=[],
        discovery_warnings=sorted(set(warnings)),
    )
