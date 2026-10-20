"""Portable desktop controller, using the existing outbound worker and v1 contracts."""

import hashlib
import json
import os
import plistlib
import secrets
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol
from urllib.error import HTTPError
from uuid import UUID

from godfather_contracts import Contract, Heartbeat, Registration, Resources
from pydantic import Field

from godfather_worker import cli
from godfather_worker.client import WorkerClient

WEB_ORIGIN = "https://app.the-godfather.ai"
API_ORIGIN = "https://api.the-godfather.ai"
AGENT_LABEL = "ai.the-godfather.worker"


class SecretStore(Protocol):
    def read(self) -> str | None: ...
    def write(self, value: str) -> None: ...
    def delete(self) -> None: ...


class Pairing(Contract):
    secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    machine_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    @property
    def challenge(self) -> str:
        return hashlib.sha256(self.secret.encode("ascii")).hexdigest()

    @property
    def browser_url(self) -> str:
        return WEB_ORIGIN + "/worker-enrollment#challenge=" + self.challenge

    def exchange(self, store: SecretStore, client: WorkerClient | None = None) -> dict[str, str]:
        transport = client or WorkerClient(API_ORIGIN, "")
        # Use the bounded no-redirect transport; no bearer secret exists before enrollment.
        result = transport.post_document("/api/v1/workers/enrollment/exchange", self)
        if not isinstance(result, dict):
            raise ValueError("Invalid enrollment response")
        for key in ("credential_id", "owner_id"):
            UUID(result[key])
        identity = {str(k): str(v) for k, v in result.items()}
        identity.update(kind="worker", token=self.machine_secret)
        store.write(json.dumps(identity))
        return identity


class Contribution(Contract):
    cpu_cores: int = Field(default=1, ge=1, le=65536)
    ram_gib: int = Field(default=2, ge=1, le=1048576)
    inference: bool = False
    primary: Literal["cpu", "inference"] = "cpu"
    shared: bool = False
    allowed_owner_ids: list[UUID] = Field(default_factory=list, max_length=128)
    allowed_workspace_ids: list[UUID] = Field(default_factory=list, max_length=128)

    def resources(self, actual: Resources) -> Resources:
        values = actual.model_dump()
        values["cpu_count"] = min(self.cpu_cores, actual.cpu_count)
        budget = self.ram_gib * 1024**3
        values["ram_bytes"] = min(actual.ram_bytes or 0, budget)
        values["available_ram_bytes"] = min(actual.available_ram_bytes or 0, budget)
        # GPU memory is not an independently enforceable budget. Do not advertise it
        # as a scheduling resource in this conservative desktop distribution.
        values["gpus"] = []
        return Resources.model_validate(values)


class LimitedClient(WorkerClient):
    def __init__(self, token: str, contribution: Contribution) -> None:
        super().__init__(API_ORIGIN, token)
        self.contribution = contribution

    def post_document(self, path: str, payload: Contract) -> object:
        if isinstance(payload, (Registration, Heartbeat)):
            payload = payload.model_copy(
                update={"resources": self.contribution.resources(payload.resources)}
            )
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
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, settings: Contribution) -> None:
        if self.running:
            raise ValueError("Worker is already running")
        if settings.shared and not (settings.allowed_owner_ids and settings.allowed_workspace_ids):
            raise ValueError("Shared work requires explicit owner and workspace IDs")
        if settings.primary == "inference" and not settings.inference:
            raise ValueError("Enable local inference before making it the primary capability")
        save_settings(self.folder / "settings.json", settings)
        arguments = [
            "--url",
            API_ORIGIN,
            "--primary",
            settings.primary,
            "--concurrency",
            "1",
            "--policy",
            "shared" if settings.shared else "dedicated",
        ]
        if settings.inference:
            provider = self.folder / "ollama.json"
            provider.write_text('[{"id":"local-ollama","provider":"ollama"}]', encoding="utf-8")
            secondary = "inference" if settings.primary == "cpu" else "cpu"
            arguments += ["--secondary", secondary, "--inference-config", str(provider)]
        for owner in settings.allowed_owner_ids:
            arguments += ["--allow-owner", str(owner)]
        for workspace in settings.allowed_workspace_ids:
            arguments += ["--allow-workspace", str(workspace)]
        self.stop_event = threading.Event()
        client = LimitedClient(self.identity["token"], settings)

        def run() -> None:
            try:
                cli.main(
                    arguments,
                    credential=self.identity,
                    stop_event=self.stop_event,
                    observer=self.observer,
                    worker_client=client,
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
    if isinstance(error, HTTPError):
        return {
            401: "This Mac's credential was revoked. Contact the owner before reconnecting.",
            403: "Access refused. Ask your administrator to check invitation, Tailscale and DNS.",
            404: "Approval unavailable, expired or used. Check the browser or reconnect.",
            409: "Name used or approval consumed. Revoke the pending entry and try a new name.",
            429: "Too many attempts. Wait one minute before trying again.",
        }.get(error.code, "The coordinator is unavailable. Try again shortly.")
    if isinstance(error, OSError) and "Keychain" in str(error):
        return str(error)
    return "Cannot connect securely. Ask your administrator to check internet, Tailscale and DNS."


def open_tailscale_setup() -> None:
    # Explicit user action opens guidance; does not install software or alter networking.
    subprocess.run(["/usr/bin/open", "https://tailscale.com/download/mac"], check=True)
