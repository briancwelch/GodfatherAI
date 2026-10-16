"""Portable discovery/transport tests; OS and GPU mocks are not physical validation."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from godfather_api.config import Settings
from godfather_api.nodes import connection_at
from godfather_contracts import Advertisement, Registration, WorkerAck
from godfather_worker import cli, discovery
from godfather_worker.client import NoRedirect, WorkerClient, retryable, validate_url
from godfather_worker.simulated import profile
from pydantic import ValidationError


@pytest.mark.parametrize("name", ["LV-01", "LV-02", "LA-01", "LA-02"])
def test_simulation_is_explicit_and_portable(name: str) -> None:
    advertisement = profile(name)
    assert advertisement.resources.source == "simulated"
    assert all(gpu.evidence == "simulated" for gpu in advertisement.resources.gpus)
    assert "SIMULATED" in advertisement.os_version
    assert advertisement.primary_capabilities
    assert Advertisement.model_validate_json(advertisement.model_dump_json()) == advertisement


@pytest.mark.parametrize(
    "system,machine,expected_os,architecture",
    [
        ("Windows", "AMD64", "windows", "x86_64"),
        ("Darwin", "arm64", "macos", "arm64"),
        ("Darwin", "x86_64", "macos", "x86_64"),
        ("Linux", "aarch64", "linux", "arm64"),
        ("Linux", "x86_64", "linux", "x86_64"),
    ],
)
def test_cross_platform_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    system: str,
    machine: str,
    expected_os: str,
    architecture: str,
) -> None:
    monkeypatch.setattr("godfather_worker.discovery.platform.system", lambda: system)
    monkeypatch.setattr("godfather_worker.discovery.platform.machine", lambda: machine)
    monkeypatch.setattr("godfather_worker.discovery.platform.processor", lambda: "Mock CPU")
    monkeypatch.setattr("godfather_worker.discovery.platform.release", lambda: "test-version")
    monkeypatch.setattr("godfather_worker.discovery.psutil.cpu_count", lambda: 8)
    monkeypatch.setattr(
        "godfather_worker.discovery.psutil.virtual_memory",
        lambda: SimpleNamespace(total=32 * 1024**3, available=24 * 1024**3),
    )
    monkeypatch.setattr("godfather_worker.discovery.psutil.cpu_percent", lambda **_: 25.0)
    monkeypatch.setattr("godfather_worker.discovery.shutil.which", lambda _: None)
    monkeypatch.setattr(discovery, "Path", lambda _: tmp_path)
    monkeypatch.setattr(discovery, "_primed", [False])

    def fake_run(*command: str) -> str:
        if command[0] == "system_profiler":
            return json.dumps(
                {
                    "SPDisplaysDataType": [
                        {"sppci_model": "Mock Apple/Intel GPU", "spdisplays_metal": "supported"}
                    ]
                }
            )
        if command[0] == "powershell.exe":
            return json.dumps({"Name": "Mock AMD GPU", "AdapterRAM": 100})
        return ""

    monkeypatch.setattr(discovery, "run", fake_run)
    result = discovery.discover()
    assert (result.os, result.architecture) == (expected_os, architecture)
    assert result.resources.source == "physical"
    assert result.resources.ram_bytes == 32 * 1024**3
    assert result.resources.cpu_percent is None
    assert discovery.discover_resources()[0].cpu_percent == 25
    if system == "Darwin":
        assert result.resources.gpus[0].backend == "metal"
        assert result.resources.gpus[0].unified_memory == (machine == "arm64")
    elif system == "Windows":
        assert result.resources.gpus[0].backend == "unknown"
        assert result.resources.gpus[0].memory_bytes is None
    else:
        assert not result.resources.gpus  # CPU-only operation is valid.


def test_linux_amd_memory_and_reported_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    device = tmp_path / "card0" / "device"
    device.mkdir(parents=True)
    for file, value in {
        "vendor": "0x1002",
        "device": "0x1234",
        "mem_info_vram_total": str(16 * 1024**3),
        "mem_info_vram_used": "1024",
    }.items():
        (device / file).write_text(value)
    monkeypatch.setattr(discovery, "Path", lambda _: tmp_path)
    monkeypatch.setattr(discovery, "run", lambda *_: "Name: gfx1100")
    gpu = discovery.linux_gpus()[0]
    assert gpu.backend == "rocm" and gpu.memory_bytes == 16 * 1024**3
    assert gpu.memory_used_bytes == 1024


def test_nvidia_unsupported_values_and_missing_platform_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        discovery,
        "run",
        lambda *_: "Mock NVIDIA, 12000, 1000, 20\nMock NVIDIA unknown, N/A, N/A, N/A\nmalformed\n",
    )
    gpus = discovery.nvidia_gpus()
    assert gpus[0].backend == "cuda" and gpus[0].evidence == "driver"
    assert gpus[0].memory_bytes == 12000 * 1024**2
    assert gpus[1].memory_bytes is None and gpus[1].utilization_percent is None
    monkeypatch.setattr(discovery, "run", lambda *_: "invalid json")
    assert discovery.macos_gpus() == [] and discovery.windows_gpus() == []


def test_discovery_subprocess_is_bounded_shell_free_and_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("godfather_worker.discovery.shutil.which", lambda _: "/mock/tool")
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        assert command == ["/mock/tool", "list"]
        return SimpleNamespace(stdout="output", returncode=0)

    monkeypatch.setattr("godfather_worker.discovery.subprocess.run", fake_run)
    assert discovery.run("ollama", "list") == "output"
    assert captured["timeout"] == 5 and "shell" not in captured
    env = captured["env"]
    assert isinstance(env, dict) and env["OLLAMA_HOST"] == "127.0.0.1:11434"
    monkeypatch.setattr(
        "godfather_worker.discovery.subprocess.run",
        Mock(side_effect=subprocess.TimeoutExpired("x", 5)),
    )
    assert discovery.run("ollama", "list") == ""


def test_local_model_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery, "discover_resources", lambda: (profile("LV-01").resources, []))
    monkeypatch.setattr("godfather_worker.discovery.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "godfather_worker.discovery.shutil.which",
        lambda tool: "/mock/ollama" if tool == "ollama" else None,
    )
    monkeypatch.setattr(
        discovery, "run", lambda *_: "NAME ID SIZE MODIFIED\nmodel:test abc 1GB now"
    )
    assert discovery.discover().installed_models[0].identifier == "model:test"
    monkeypatch.setattr(discovery, "run", lambda *_: "")
    assert "ollama-model-inventory-unavailable" in discovery.discover().discovery_warnings


def test_unsupported_host_probes_preserve_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "godfather_worker.discovery.psutil.cpu_count", Mock(side_effect=NotImplementedError)
    )
    monkeypatch.setattr(
        "godfather_worker.discovery.psutil.virtual_memory", Mock(side_effect=PermissionError)
    )
    monkeypatch.setattr(discovery, "nvidia_gpus", lambda: [])
    monkeypatch.setattr(discovery, "windows_gpus", lambda: [])
    monkeypatch.setattr("godfather_worker.discovery.platform.system", lambda: "Windows")
    resources, warnings = discovery.discover_resources()
    assert resources.source == "physical" and resources.cpu_count == 1
    assert resources.ram_bytes is None and resources.cpu_percent is None
    assert "host-telemetry-unavailable" in warnings and "cpu-count-unavailable" in warnings
    assert discovery.metal_reported("spdisplays_metal3")
    assert not discovery.metal_reported("spdisplays_metalunsupported")
    assert not discovery.metal_reported("not supported")


@pytest.mark.parametrize(
    "elapsed,expected",
    [(0, "online"), (19.99, "online"), (20, "suspect"), (29.99, "suspect"), (30, "offline")],
)
def test_health_exact_boundaries(elapsed: float, expected: str) -> None:
    last = datetime.now(UTC)
    assert (
        connection_at(last, last + timedelta(seconds=elapsed), Settings(database_password="test"))
        == expected
    )


def test_contract_and_configuration_reject_invalid_inputs() -> None:
    payload = profile("LV-01").model_dump()
    with pytest.raises(ValidationError):
        Registration.model_validate({**payload, "session_id": "bad"})
    with pytest.raises(ValidationError):
        Advertisement.model_validate({**payload, "secondary_capabilities": ["coding"]})
    with pytest.raises(ValidationError):
        Settings(database_password="test", suspect_after_seconds=30)
    with pytest.raises(ValidationError):
        Advertisement.model_validate(
            {**payload, "resources": {**payload["resources"], "cpu_percent": float("nan")}}
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://100.64.0.1:8000",
        "https://user:secret@coordinator",
        "file:///tmp/a",
        "https://coordinator/?token=secret",
        "https://coordinator/path",
    ],
)
def test_transport_refuses_unsafe_origins(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)


def test_transport_keeps_tls_and_does_not_forward_credentials() -> None:
    assert validate_url("https://coordinator.example/") == "https://coordinator.example"
    assert validate_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert WorkerClient("http://localhost", "token").opener
    NoRedirect().redirect_request(
        Request("http://localhost"), None, 302, "Found", Message(), "https://elsewhere"
    )
    assert retryable(HTTPError("", 503, "", Message(), None))
    assert not retryable(HTTPError("", 401, "", Message(), None))


def test_worker_reconnects_with_same_session_and_obeys_coordinator_interval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    credential = tmp_path / "worker.json"
    credential.write_text(json.dumps({"kind": "worker", "token": "secret"}))
    calls: list[tuple[str, object]] = []
    waits: list[int] = []
    ack = WorkerAck(
        node_id="12345678-1234-1234-1234-123456789abc",
        state="online",
        connection_status="online",
        heartbeat_interval_seconds=10,
    )

    class Client:
        def __init__(self, url: str, token: str) -> None:
            assert token == "secret"

        def post(self, path: str, payload: object) -> WorkerAck:
            calls.append((path, payload))
            if len(calls) == 2:
                raise URLError("secret internal error")
            if len(calls) == 4:
                raise KeyboardInterrupt
            return ack

    class Stop:
        def is_set(self) -> bool:
            return False

        def wait(self, seconds: int) -> None:
            waits.append(seconds)

    monkeypatch.setattr(cli, "WorkerClient", Client)
    monkeypatch.setattr("godfather_worker.cli.threading.Event", Stop)
    monkeypatch.setattr(
        "sys.argv", ["worker", "--credential-file", str(credential), "--simulate", "LA-01"]
    )
    assert cli.main() == 0
    assert calls[0][0] == calls[2][0] == "/api/v1/workers/register"
    assert calls[0][1] == calls[2][1]
    assert waits == [10, 1, 10]
    assert "secret" not in capsys.readouterr().out
