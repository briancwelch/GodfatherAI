"""Owner-approved managed llama.cpp setup; host paths and private keys stay local."""

import ipaddress
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from godfather_contracts import GPU, Contract, SharedInferenceGroup

SETUP_RUNTIME = "shared-engine-setup-v1"
ACTIVE_PREFIX = "managed-engine:"
ENGINE_VERSION = "b11846"
DeviceID = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$", max_length=100)]


def private_address(value: str) -> str:
    address = ipaddress.ip_address(value)
    networks = (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "fc00::/7",
        "::1/128",
    )
    if not any(address in ipaddress.ip_network(net) for net in networks):
        raise ValueError("Choose a local or private-network address")
    return str(address)


class EngineDevice(Contract):
    id: DeviceID
    name: str = Field(min_length=1, max_length=200)
    backend: Literal["cpu", "cuda", "metal", "vulkan", "rocm", "unknown"]
    memory_bytes: int | None = Field(default=None, ge=0)

    def advertisement(self) -> GPU | None:
        if self.backend == "cpu":
            return None
        return GPU(
            name=self.name[:100],
            backend=self.backend if self.backend in ("cuda", "metal", "rocm") else "unknown",
            evidence="reported",
            memory_bytes=self.memory_bytes,
        )


class EngineCreate(Contract):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=100)
    mode: Literal["single_host", "local_network", "wide_area"]
    node_ids: list[UUID] = Field(min_length=1, max_length=64)

    @field_validator("node_ids")
    @classmethod
    def distinct(cls, values: list[UUID]) -> list[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("Choose each computer once")
        return values


class EngineProposal(EngineCreate):
    id: UUID
    leader_node_id: UUID
    engine_version: Literal["b11846"] = "b11846"

    @property
    def model_alias(self) -> str:
        return "shared-" + self.id.hex

    @model_validator(mode="after")
    def topology(self) -> "EngineProposal":
        if self.leader_node_id not in self.node_ids:
            raise ValueError("The leader must participate")
        if (self.mode == "single_host") != (len(self.node_ids) == 1):
            raise ValueError("Choose one computer for local GPUs, or several for network sharing")
        return self


class EngineApproval(Contract):
    group_id: UUID
    devices: list[EngineDevice] = Field(min_length=1, max_length=32)
    host: str = Field(max_length=64)
    port: int = Field(ge=1024, le=65535)
    certificate: str = Field(min_length=100, max_length=8192, repr=False)

    _private_host = field_validator("host")(private_address)

    @field_validator("devices")
    @classmethod
    def distinct_devices(cls, devices: list[EngineDevice]) -> list[EngineDevice]:
        if len({d.id for d in devices}) != len(devices):
            raise ValueError("Choose each device once")
        return devices


class EngineAction(Contract):
    group_id: UUID
    action: Literal["start", "stop", "withdraw"]


class EngineDelete(Contract):
    group_id: UUID


class EngineReport(Contract):
    group_id: UUID
    generation: int = Field(ge=0)
    phase: Literal["waiting", "starting", "ready", "stopped", "error"]
    error_code: (
        Literal["engine_failed", "peer_unavailable", "setup_changed", "runtime_missing"] | None
    ) = None


class EngineMember(Contract):
    node_id: UUID
    name: str
    owner: str
    approved: bool
    devices: list[EngineDevice] = Field(default_factory=list, max_length=32)
    host: str | None = None
    port: int | None = None
    certificate: str | None = Field(default=None, repr=False)
    phase: str = "waiting"
    error_code: str | None = None


class EngineGroup(Contract):
    proposal: EngineProposal
    members: list[EngineMember] = Field(max_length=64)
    desired_running: bool
    generation: int = Field(ge=0)
    group: SharedInferenceGroup | None = None


class LocalEngineConsent(Contract):
    """Owner-local execution scope. Never serialized into coordinator job state."""

    proposal: EngineProposal
    node_id: UUID
    credential_id: UUID
    devices: list[EngineDevice] = Field(min_length=1, max_length=32)
    backend: Literal["cpu", "vulkan", "metal"]
    host: str = Field(max_length=64)
    port: int = Field(ge=1024, le=65535)
    model_path: str | None = Field(default=None, max_length=32768, repr=False)
    context_size: int = Field(default=2048, ge=256, le=32768)
    threads: int = Field(default=2, ge=1, le=65536)
    _private_host = field_validator("host")(private_address)

    @model_validator(mode="after")
    def scoped(self) -> "LocalEngineConsent":
        if self.node_id not in self.proposal.node_ids:
            raise ValueError("Only a participating computer can approve")
        if self.node_id == self.proposal.leader_node_id and not self.model_path:
            raise ValueError("Choose an installed GGUF model on the leader")
        if len({d.id for d in self.devices}) != len(self.devices):
            raise ValueError("Choose each device once")
        return self
