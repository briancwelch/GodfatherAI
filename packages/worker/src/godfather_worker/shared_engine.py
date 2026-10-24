"""Managed local llama.cpp processes and authenticated peer RPC bridges."""

import json
import re
import socket
import subprocess
import threading
from contextlib import suppress
from pathlib import Path
from time import monotonic
from urllib.error import URLError
from urllib.request import Request

from godfather_contracts import GPU
from godfather_contracts.shared_engine import EngineGroup, LocalEngineConsent
from godfather_model_gateway import ProviderConfig

from godfather_worker.client import WorkerClient
from godfather_worker.llama_runtime import Runtime, environment, gguf, run_probe
from godfather_worker.shared_engine_transport import Bridge, contexts, free_port, hostname


def remote_devices(output: str, endpoints: list[str]) -> list[str]:
    """Pinned native builds expose RPC0 with the endpoint in its description."""
    inventory = output.split("Available devices:", 1)[-1]
    matches = [
        match
        for line in inventory.splitlines()
        if (match := re.match(r"\s*(RPC\d+(?:\[[^\s]+\])?):\s+(.+)$", line))
    ]
    if not matches or any(
        not any(endpoint in m[1] or endpoint in m[2] for m in matches) for endpoint in endpoints
    ):
        raise ValueError("An approved peer's devices could not be reached securely")
    return list(dict.fromkeys(m[1] for m in matches))


class Engine:
    def __init__(
        self, folder: Path, consent: LocalEngineConsent, runtime: Runtime, group: EngineGroup
    ) -> None:
        self.folder, self.consent, self.runtime, self.group = folder, consent, runtime, group
        self.processes: list[subprocess.Popen[bytes]] = []
        self.bridges: list[Bridge] = []
        self.stop_event = threading.Event()
        self.guard = threading.RLock()
        self.provider: ProviderConfig | None = None

    @property
    def alive(self) -> bool:
        return bool(self.processes) and all(p.poll() is None for p in self.processes)

    def spawn(self, executable: Path, arguments: list[str]) -> None:
        with self.guard:
            if self.stop_event.is_set():
                raise ValueError("Shared engine startup cancelled")
            process = subprocess.Popen(
                [str(executable), *arguments],
                cwd=executable.parent,
                env=environment(self.runtime.root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
            self.processes.append(process)

    def add_bridge(self, bridge: Bridge) -> None:
        with self.guard:
            if self.stop_event.is_set():
                bridge.close()
                raise ValueError("Shared engine startup cancelled")
            self.bridges.append(bridge)

    def wait_port(self, port: int, timeout: float = 15) -> None:
        deadline = monotonic() + timeout
        while monotonic() < deadline and not self.stop_event.is_set():
            if not self.alive:
                raise ValueError("The shared engine process stopped during setup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return
            except OSError:
                self.stop_event.wait(0.1)
        raise ValueError("The shared engine did not become available")

    def start(self) -> None:
        plan, local = self.group.proposal, self.consent
        if plan != local.proposal or self.group.group is None:
            raise ValueError("The group changed; approve the current setup locally again")
        own = next((m for m in self.group.members if m.node_id == local.node_id), None)
        if own is None or not own.approved or own.devices != local.devices:
            raise ValueError("This computer's local device approval no longer matches")
        try:
            if local.node_id != plan.leader_node_id:
                self.start_peer()
            else:
                self.start_leader()
        except Exception:
            self.stop()
            raise

    def start_peer(self) -> None:
        local = self.consent
        leader = next(
            m for m in self.group.members if m.node_id == self.group.proposal.leader_node_id
        )
        if not leader.certificate:
            raise ValueError("The initiating computer has not approved its identity")
        raw_port = free_port()
        self.spawn(
            self.runtime.rpc,
            [
                "--host",
                "127.0.0.1",
                "--port",
                str(raw_port),
                "--threads",
                str(local.threads),
                "--device",
                ",".join(d.id for d in local.devices),
            ],
        )
        self.wait_port(raw_port)
        context = contexts(self.folder, local.node_id, local.proposal.id, leader.certificate, True)
        self.add_bridge(
            Bridge(
                local.host,
                local.port,
                ("127.0.0.1", raw_port),
                context,
                leader.certificate,
                server=True,
            )
        )

    def start_leader(self) -> None:
        local, plan = self.consent, self.group.proposal
        model = gguf(Path(local.model_path or ""))
        endpoints = []
        for peer in self.group.members:
            if peer.node_id == local.node_id:
                continue
            if (
                not peer.approved
                or peer.phase != "ready"
                or not peer.host
                or not peer.port
                or not peer.certificate
            ):
                raise ValueError("Wait for the participating computers to finish local setup")
            context = contexts(self.folder, local.node_id, plan.id, peer.certificate, False)
            bridge = Bridge(
                "127.0.0.1",
                0,
                (peer.host, peer.port),
                context,
                peer.certificate,
                server=False,
                peer_name=hostname(peer.node_id, plan.id),
            )
            self.add_bridge(bridge)
            endpoints.append(f"127.0.0.1:{bridge.port}")
        selected = [d.id for d in local.devices if d.backend != "cpu"]
        if endpoints:
            output = run_probe(self.runtime, ["--rpc", ",".join(endpoints), "--list-devices"])
            selected += remote_devices(output, endpoints)
        port = free_port()
        arguments = ["--offline", "--no-webui", "--no-agent", "--no-mmproj", "--log-disable"]
        if endpoints:
            arguments += ["--rpc", ",".join(endpoints)]
        arguments += [
            "--model",
            str(model),
            "--alias",
            plan.model_alias,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--parallel",
            "1",
            "--ctx-size",
            str(local.context_size),
            "--threads",
            str(local.threads),
            "--device",
            ",".join(selected) or "none",
            "--n-gpu-layers",
            "999" if selected else "0",
            "--split-mode",
            "layer",
        ]
        self.spawn(self.runtime.server, arguments)
        client = WorkerClient(f"http://127.0.0.1:{port}", "")
        deadline = monotonic() + 180
        while monotonic() < deadline and not self.stop_event.is_set():
            if not self.alive:
                raise ValueError(
                    "llama.cpp stopped. Check the selected GGUF model, available "
                    "memory and backend driver."
                )
            try:
                with client.opener.open(Request(client.url + "/health"), timeout=2) as response:
                    health = response.read(4097)
                if len(health) > 4096 or json.loads(health).get("status") != "ok":
                    self.stop_event.wait(0.25)
                    continue
                with client.opener.open(Request(client.url + "/v1/models"), timeout=2) as response:
                    raw = response.read(1024**2 + 1)
                if len(raw) <= 1024**2:
                    data = json.loads(raw)
                    if any(
                        m.get("id") == plan.model_alias
                        for m in data.get("data", [])
                        if isinstance(m, dict)
                    ):
                        self.provider = ProviderConfig(
                            id="shared-" + plan.id.hex,
                            provider="openai_compatible",
                            url=client.url + "/v1",
                            shared_inference_group_id=plan.id,
                            chat_enabled=True,
                            stream_enabled=True,
                            discovery_models=[plan.model_alias],
                        )
                        return
            except (OSError, URLError, ValueError, AttributeError):
                pass
            self.stop_event.wait(0.25)
        raise ValueError(
            "The model did not finish loading. Check memory, peers and the selected model."
        )

    def gpu_advertisement(self) -> list[GPU]:
        return [
            gpu for device in self.consent.devices if (gpu := device.advertisement()) is not None
        ]

    def stop(self) -> None:
        self.stop_event.set()
        with self.guard:
            bridges, self.bridges = self.bridges, []
            processes, self.processes = self.processes, []
        for bridge in bridges:
            bridge.close()
        for process in processes:
            if process.poll() is None:
                with suppress(OSError):
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        self.provider = None
