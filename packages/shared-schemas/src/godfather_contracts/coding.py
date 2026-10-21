"""Bounded coding output and worker-local repository authorization."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator

from godfather_contracts import Contract

CODING_RUNTIME = "coding-sandbox-v1"
REPOSITORY_PREFIX = "coding-repository/"


class CodingWorkspace(Contract):
    id: UUID
    name: str = Field(min_length=1, max_length=200)


class CodingSetupOptions(Contract):
    owner_id: UUID
    workspaces: list[CodingWorkspace] = Field(max_length=128)


class FileEdit(Contract):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=32768)

    @field_validator("path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        parts = value.split("/")
        stems = [p.split(".", 1)[0].lower() for p in parts]
        reserved = {
            "con",
            "nul",
            "prn",
            "aux",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }
        if (
            value.startswith("/")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value
            or ":" in value
            or any(p in ("", ".", "..") or p.endswith((".", " ")) for p in parts)
            or any(
                p.lower().startswith((".git", ".env", ".ssh", ".aws", ".codex", ".agents"))
                for p in parts
            )
            or any(p in reserved for p in stems)
        ):
            raise ValueError("Unsafe workspace path")
        return value


class CodingPlan(Contract):
    summary: str = Field(min_length=1, max_length=8192)
    edits: list[FileEdit] = Field(max_length=32)


class TestOutcome(Contract):
    command: list[str] = Field(min_length=1, max_length=32)
    exit_code: int
    output: str = Field(max_length=16384)


class CodingOutput(Contract):
    summary: str = Field(min_length=1, max_length=8192)
    repository_id: UUID
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    files_changed: list[str] = Field(max_length=128)
    diff: str = Field(max_length=131072)
    tests: list[TestOutcome] = Field(max_length=16)
    network: str = "disabled"
    isolation: str = "disposable container workspace"
    search_matches: list[dict[str, str | int]] = Field(default_factory=list, max_length=32)


class CodingRepository(Contract):
    id: UUID
    name: str = Field(default="Approved repository", min_length=1, max_length=100)
    path: Path = Field(repr=False)
    allow_apply: bool = False
    image: str = Field(pattern=r"^(?:[a-zA-Z0-9][a-zA-Z0-9._:/-]*@)?sha256:[0-9a-f]{64}$")
    allowed_user_ids: list[UUID] = Field(min_length=1, max_length=128)
    allowed_workspace_ids: list[UUID] = Field(min_length=1, max_length=128)
    files: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        min_length=1, max_length=128
    )
    commands: list[list[Annotated[str, Field(min_length=1, max_length=1000)]]] = Field(
        default_factory=list, max_length=16
    )
