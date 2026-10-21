"""Versioned, capability-negotiated actions on immutable job results.

New result renderers do not require worker changes. Only locally implemented,
advertised action kinds may execute; this protocol never transports executable code.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from godfather_contracts import Contract
from godfather_contracts.agents import ArtifactReference

ACTION_RUNTIME = "result-actions-v1"
PATCH_RUNTIME = "result-action-coding-patch-v1"
TARGET_PREFIX = "apply-repository/"


class ResultActionInput(Contract):
    protocol_version: Literal[1] = 1
    action: Literal["coding.patch.apply"] = "coding.patch.apply"
    source_job_id: UUID
    artifact: ArtifactReference
    node_id: UUID
    repository_id: UUID


class ResultActionRequest(Contract):
    artifact_id: UUID
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class ResultActionOutput(Contract):
    protocol_version: Literal[1] = 1
    action: Literal["coding.patch.apply"] = "coding.patch.apply"
    source_job_id: UUID
    state: Literal["applied", "blocked"]
    summary: str = Field(min_length=1, max_length=1000)
    files: list[str] = Field(default_factory=list, max_length=128)
