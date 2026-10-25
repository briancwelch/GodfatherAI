"""Portable desktop controller, using the existing outbound worker and v1 contracts."""

import hashlib
import json
import os
import plistlib
import secrets
import socket
import ssl
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol
from urllib.error import HTTPError
from urllib.parse import urlsplit
from uuid import UUID

from godfather_contracts import (
    Contract,
    HardwareMeasurements,
    Heartbeat,
    Label,
    Registration,
    Resources,
)
from godfather_contracts.coding import CodingRepository
from godfather_model_gateway import ModelMemoryProfile, ProviderConfig
from pydantic import Field, field_validator

from godfather_worker import cli
from godfather_worker.client import WorkerClient
from godfather_worker.workloads import WorkloadConfig

if TYPE_CHECKING:
    from godfather_worker.shared_engine import Engine

WEB_ORIGIN = "https://app.the-godfather.ai"
API_ORIGIN = "https://api.the-godfather.ai"
AGENT_LABEL = "ai.the-godfather.worker"


def coordinator_origin(value: str) -> str:
    """One explicit origin; never follow a redirect with machine credentials."""
    value = value.strip().rstrip("/")
    url = urlsplit(value)
    local = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
    if (
        not (url.scheme == "https" or local)
        or not url.hostname
        or url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
    ):
        raise ValueError("Enter an HTTPS Command Center address, for example https://example.com")
    _ = url.port  # Reject malformed ports before any request.
    return value


class SecretStore(Protocol):
    def read(self) -> str | None: ...
    def write(self, value: str) -> None: ...
    def delete(self) -> None: ...


class Exchange(Contract):
    secret: str = Field(repr=False)
    machine_secret: str = Field(repr=False)


class Pairing(Contract):
    origin: str = Field(default=WEB_ORIGIN, exclude=True)
    secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    machine_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    @property
    def challenge(self) -> str:
        return hashlib.sha256(self.secret.encode("ascii")).hexdigest()

    @property
    def browser_url(self) -> str:
        return coordinator_origin(self.origin) + "/worker-enrollment#challenge=" + self.challenge

    def exchange(self, store: SecretStore, client: WorkerClient | None = None) -> dict[str, str]:
        transport = client or WorkerClient(coordinator_origin(self.origin), "")
        # Use the bounded no-redirect transport; no bearer secret exists before enrollment.
        # Origin is local metadata, not part of the versioned enrollment payload.
        result = transport.post_document(
            "/api/v1/workers/enrollment/exchange",
            Exchange(secret=self.secret, machine_secret=self.machine_secret),
        )
        if not isinstance(result, dict):
            raise ValueError("Invalid enrollment response")
        for key in ("credential_id", "owner_id"):
            UUID(result[key])
        identity = {str(k): str(v) for k, v in result.items()}
        identity.update(
            kind="worker", token=self.machine_secret, origin=coordinator_origin(self.origin)
        )
        store.write(json.dumps(identity))
        return identity


class Contribution(Contract):
    cpu_cores: int = Field(default=1, ge=1, le=65536)
    ram_gib: int = Field(default=2, ge=1, le=1048576)
    inference: bool = False
    model_installation: bool = False
    runtime_installation: bool = False
    account_providers: bool = False
    cloud_images: bool = False
    primary: Literal["cpu", "inference"] = "cpu"
    shared: bool = False
    share_with_workspaces: bool = False
    allowed_owner_ids: list[UUID] = Field(default_factory=list, max_length=128)
    allowed_workspace_ids: list[UUID] = Field(default_factory=list, max_length=128)
    repositories: list[CodingRepository] = Field(default_factory=list, max_length=8, repr=False)
    workloads: WorkloadConfig | None = None
    local_providers: list[ProviderConfig] = Field(default_factory=list, max_length=7)
    ollama_memory_profiles: dict[Label, ModelMemoryProfile] = Field(
        default_factory=dict, max_length=128
    )

    @field_validator("local_providers")
    @classmethod
    def local_only(cls, providers: list[ProviderConfig]) -> list[ProviderConfig]:
        if len({p.id for p in providers}) != len(providers):
            raise ValueError("Local server aliases must be unique")
        for provider in providers:
            if (
                provider.provider != "openai_compatible"
                or urlsplit(provider.url).hostname not in ("127.0.0.1", "localhost", "::1")
                or provider.api_key_env
                or provider.connection_id
                or provider.shared_inference_group_id
                or provider.id == "local-ollama"
            ):
                raise ValueError("Scanned local servers must be owner-local, without account keys")
        return providers

    def with_workspace_contribution(self, enabled: bool) -> "Contribution":
        """One explicit local choice; legacy scopes and unrelated permissions survive."""
        return self.model_copy(
            update={
                "share_with_workspaces": enabled,
                "shared": enabled,
                "inference": True if enabled else self.inference,
            }
        )

    def resources(self, actual: Resources) -> Resources:
        values = actual.model_dump()
        values["hardware"] = (
            actual.hardware.model_dump()
            if actual.hardware
            else HardwareMeasurements(
                cpu_count=actual.cpu_count,
                ram_bytes=actual.ram_bytes,
                available_ram_bytes=actual.available_ram_bytes,
                gpus=actual.gpus,
            ).model_dump()
        )
        values["cpu_count"] = min(self.cpu_cores, actual.cpu_count)
        budget = self.ram_gib * 1024**3
        values["ram_bytes"] = (
            min(actual.ram_bytes, budget) if actual.ram_bytes is not None else None
        )
        values["available_ram_bytes"] = (
            min(actual.available_ram_bytes, budget, actual.ram_bytes)
            if actual.available_ram_bytes is not None and actual.ram_bytes is not None
            else None
        )
        # GPU memory is not an independently enforceable budget. Do not advertise it
        # as a scheduling resource in this conservative desktop distribution.
        values["gpus"] = []
        return Resources.model_validate(values)


def first_run_contribution(actual: Resources) -> Contribution:
    """Only a fresh, unpaired install. Connect visibly approves these contributions."""
    return Contribution(
        cpu_cores=actual.cpu_count,
        ram_gib=max(1, (actual.ram_bytes or 2 * 1024**3) // 1024**3),
        inference=True,
        shared=True,
        share_with_workspaces=True,
    )


class LimitedClient(WorkerClient):
    def __init__(
        self,
        token: str,
        contribution: Contribution,
        origin: str = API_ORIGIN,
        engine: "Engine | None" = None,
    ) -> None:
        super().__init__(coordinator_origin(origin), token)
        self.contribution = contribution
        self.engine = engine

    def post_document(self, path: str, payload: Contract) -> object:
        if isinstance(payload, (Registration, Heartbeat)):
            resources = self.contribution.resources(payload.resources)
            if self.engine is not None and self.engine.alive:
                resources = resources.model_copy(update={"gpus": self.engine.gpu_advertisement()})
            payload = payload.model_copy(update={"resources": resources})
        return super().post_document(path, payload)


def save_settings(path: Path, settings: Contribution) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(settings.model_dump_json())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def login_startup(enable: bool, executable: Path, agent: Path) -> None:
    """Only this user's product LaunchAgent. No launchctl/root or host changes."""
    if enable:
        if (
            executable.parent.name != "MacOS"
            or not executable.is_file()
            or str(executable).startswith("/Volumes/")
        ):
            raise ValueError("Install the worker app before enabling login startup")
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_bytes(
            plistlib.dumps(
                {
                    "Label": AGENT_LABEL,
                    "ProgramArguments": [str(executable), "--login"],
                    "RunAtLoad": True,
                    "KeepAlive": False,
                }
            )
        )
        os.chmod(agent, 0o600)
    else:
        agent.unlink(missing_ok=True)


class Controller:
    def __init__(
        self, identity: dict[str, str], folder: Path, observer: Callable[..., None]
    ) -> None:
        self.identity, self.folder, self.observer = identity, folder, observer
        # Existing app identities without an origin retain the old private API endpoint.
        self.origin = coordinator_origin(identity.get("origin", API_ORIGIN))
        self.stop_event = threading.Event()
        self.maintenance_event = threading.Event()
        self.thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, settings: Contribution, engine: "Engine | None" = None) -> None:
        if self.running:
            raise ValueError("Worker is already running")
        if (
            settings.shared
            and not settings.share_with_workspaces
            and not (settings.allowed_owner_ids and settings.allowed_workspace_ids)
        ):
            raise ValueError("Shared work requires explicit owner and workspace IDs")
        if settings.primary == "inference" and not settings.inference:
            raise ValueError("Enable local inference before making it the primary capability")
        if settings.model_installation and not settings.inference:
            raise ValueError("Enable local AI models before allowing model downloads")
        if settings.runtime_installation and not settings.model_installation:
            raise ValueError("Enable model downloads before allowing Ollama runtime setup")
        if settings.cloud_images and not settings.account_providers:
            raise ValueError("Enable account API connections before cloud image generation")
        if settings.repositories:
            owner = UUID(self.identity["owner_id"])
            if not settings.inference and not settings.account_providers:
                raise ValueError(
                    "Enable local AI or your account API connections before using coding projects"
                )
            if any(r.allowed_user_ids != [owner] for r in settings.repositories):
                raise ValueError("Desktop coding projects must belong to the connected owner")
            if len({r.id for r in settings.repositories}) != len(settings.repositories):
                raise ValueError("Each coding project must have a distinct identity")
        save_settings(self.folder / "settings.json", settings)
        budgets = settings
        if engine is not None:
            if not engine.alive or engine.group.group is None:
                raise ValueError("The shared engine must be ready before contributing")
            # Keep saved choices; reserve this session for the approved shared model.
            settings = settings.model_copy(
                update={
                    "primary": "inference",
                    "inference": False,
                    "account_providers": False,
                    "cloud_images": False,
                    "model_installation": False,
                    "runtime_installation": False,
                    "repositories": [],
                    "workloads": None,
                }
            )
        arguments = [
            "--url",
            self.origin,
            "--primary",
            settings.primary,
            "--concurrency",
            "1",
            "--policy",
            "shared" if settings.shared else "dedicated",
            "--shared-engine-setup",
        ]
        if engine is not None:
            assert engine.group.group is not None
            group_path = self.folder / "shared-engine/active-group.json"
            group_path.write_text(
                json.dumps([engine.group.group.model_dump(mode="json")]), encoding="utf-8"
            )
            arguments += [
                "--shared-inference-config",
                str(group_path),
                "--managed-shared-inference",
                str(engine.group.proposal.id),
            ]
            if engine.provider:
                provider_path = self.folder / "shared-engine/active-provider.json"
                provider_path.write_text(
                    json.dumps([engine.provider.model_dump(mode="json")]), encoding="utf-8"
                )
                arguments += ["--inference-config", str(provider_path)]
        if settings.inference:
            provider = self.folder / "ollama.json"
            provider.write_text(
                json.dumps(
                    [
                        {
                            "id": "local-ollama",
                            "provider": "ollama",
                            "memory_profiles": {
                                name: profile.model_dump(mode="json")
                                for name, profile in settings.ollama_memory_profiles.items()
                            },
                        },
                        *(p.model_dump(mode="json") for p in settings.local_providers),
                    ]
                ),
                encoding="utf-8",
            )
            secondary = "inference" if settings.primary == "cpu" else "cpu"
            arguments += ["--secondary", secondary, "--inference-config", str(provider)]
        if settings.model_installation:
            arguments += ["--allow-model-installation"]
        if settings.runtime_installation:
            arguments += ["--allow-runtime-installation", "--runtime-folder", str(self.folder)]
        if (
            settings.inference
            or settings.account_providers
            or settings.repositories
            or settings.workloads
        ):
            # Model-only agents need the workflow protocol too. No host tools are
            # granted here; coding/data tools retain their separate owner opt-ins.
            arguments += ["--execute-workflows"]
        if settings.repositories:
            from godfather_worker.coding_setup import save_repositories

            coding_path = self.folder / "coding.json"
            save_repositories(coding_path, settings.repositories)
            arguments += [
                "--coding-config",
                str(coding_path),
                "--allow-tool-permission",
                "coding.workspace",
            ]
        if settings.account_providers:
            arguments += ["--account-providers"]
        if settings.cloud_images:
            arguments += ["--cloud-images", "--allow-tool-permission", "images.generate"]
        if settings.workloads:
            config_path = self.folder / "workloads.json"
            config_path.write_text(settings.workloads.model_dump_json(), encoding="utf-8")
            config_path.chmod(0o600)
            arguments += ["--workload-config", str(config_path)]
            if settings.workloads.image:
                arguments += ["--allow-tool-permission", "data.analyze"]
            if settings.workloads.images:
                arguments += ["--allow-tool-permission", "images.generate"]
        for owner in settings.allowed_owner_ids:
            arguments += ["--allow-owner", str(owner)]
        if settings.shared and settings.share_with_workspaces:
            arguments += ["--share-with-workspaces"]
        for workspace in dict.fromkeys(
            [*settings.allowed_workspace_ids]
            + [w for r in settings.repositories for w in r.allowed_workspace_ids]
        ):
            arguments += ["--allow-workspace", str(workspace)]
        self.stop_event = threading.Event()
        self.maintenance_event.clear()
        client = LimitedClient(self.identity["token"], budgets, self.origin, engine)

        def run() -> None:
            try:
                cli.main(
                    arguments,
                    credential=self.identity,
                    stop_event=self.stop_event,
                    observer=self.observer,
                    worker_client=client,
                    maintenance_event=self.maintenance_event,
                )
            except Exception:
                self.observer("worker.unexpected_error")
            finally:
                self.observer("worker.stopped")

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()


def connection_error(error: Exception) -> str:
    from urllib.error import URLError

    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return (
            "HTTPS certificate verification failed. Check this computer's date/time "
            "and whether its network inspects HTTPS."
        )
    if isinstance(reason, socket.gaierror):
        return "Command Center address could not be resolved. Check the address and DNS connection."
    if isinstance(reason, (TimeoutError, ConnectionError)):
        return (
            "Command Center did not respond. Check your internet connection and try Connect again."
        )
    if isinstance(error, HTTPError):
        return {
            401: "This computer's credential was revoked. Contact your administrator.",
            403: "Access refused. Ask your administrator to check invitation and node permissions.",
            404: "Approval unavailable, expired or used. Check the browser or reconnect.",
            409: "Name used or approval consumed. Revoke the pending entry and try a new name.",
            429: "Too many attempts. Wait one minute before trying again.",
        }.get(error.code, "The coordinator is unavailable. Try again shortly.")
    if isinstance(error, OSError) and "Keychain" in str(error):
        return str(error)
    if isinstance(error, OSError) and "OS credential store" in str(error):
        return "Unlock your operating system credential store, then reconnect."
    return "Cannot connect securely. Check the coordinator address and internet connection."


def open_tailscale_setup() -> None:
    # Explicit user action opens guidance; does not install software or alter networking.
    subprocess.run(["/usr/bin/open", "https://tailscale.com/download/mac"], check=True)
