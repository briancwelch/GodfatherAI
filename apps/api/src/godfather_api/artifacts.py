"""Immutable, size-bounded local artifact backend; PostgreSQL owns visibility."""

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol
from uuid import UUID

from godfather_contracts.workloads import MAX_ARTIFACT_BYTES


class ArtifactError(Exception):
    pass


def encode(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class ArtifactStore(Protocol):
    def write(self, artifact_id: UUID, data: bytes) -> None: ...
    def read(self, artifact_id: UUID, checksum: str, size_bytes: int) -> bytes: ...


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve() / "v1"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, artifact_id: UUID) -> Path:
        # Callers supply parsed UUIDs, never an owner-provided filesystem path.
        if not isinstance(artifact_id, UUID):
            raise ArtifactError("Invalid artifact identity")
        path = self.root / (artifact_id.hex + ".json")
        if path.is_symlink():
            raise ArtifactError("Artifact symlinks are not permitted")
        return path

    def write(self, artifact_id: UUID, data: bytes) -> None:
        if not 0 < len(data) <= MAX_ARTIFACT_BYTES:
            raise ArtifactError("Artifact size limit exceeded")
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            with os.fdopen(os.open(self.path(artifact_id), flags, 0o600), "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if os.name != "nt":
                descriptor = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except OSError:
            raise ArtifactError("Artifact write failed") from None

    def read(self, artifact_id: UUID, checksum: str, size_bytes: int) -> bytes:
        try:
            with self.path(artifact_id).open("rb") as handle:
                data = handle.read(MAX_ARTIFACT_BYTES + 1)
        except OSError:
            raise ArtifactError("Artifact unavailable") from None
        if (
            len(data) != size_bytes
            or len(data) > MAX_ARTIFACT_BYTES
            or hashlib.sha256(data).hexdigest() != checksum
        ):
            raise ArtifactError("Artifact integrity check failed")
        return data
