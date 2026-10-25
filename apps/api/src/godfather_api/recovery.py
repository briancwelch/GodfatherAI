"""Offline recovery inventory, separately encrypted configuration, and read-only checks.

No HTTP endpoints, provider calls, migrations, scheduling, or automatic restore.
The recovery key is independent of the provider vault key and never enters a dump.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from godfather_agent_runtime import WorkflowError, state_for
from godfather_contracts.agents import WorkflowAssignment, WorkflowState
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from godfather_api.account_providers import decrypt_key
from godfather_api.artifacts import ArtifactError, LocalArtifactStore
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.migrations import migration_head
from godfather_api.models import (
    AccountProviderKey,
    Agent,
    Artifact,
    Attempt,
    Checkpoint,
    Job,
    WorkflowRun,
)
from godfather_api.workflow_service import agent_view, load_artifact, workflow_assignment

DATA_FILES = ("database.dump", "artifacts.tar.gz", "release.env", "manifest.json")
AAD = b"godfather-configuration-recovery-v1"
MAX_CONFIGURATION = 64 * 1024


class RecoveryError(Exception):
    """Only fixed, secret-free messages may cross the CLI boundary."""


class Inventory(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    format_version: Literal[1] = 1
    created_at: str
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    migration_head: str = Field(min_length=1, max_length=100)
    files: dict[str, str]


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise RecoveryError("Recovery input is missing or is not a regular file.")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def settings_digest(settings: Settings) -> str:
    # Hash the complete effective API configuration, including otherwise masked secrets.
    # This detects shell/Compose overrides absent from the recovered environment file.
    values = settings.model_dump(mode="json")
    for name in type(settings).model_fields:
        value = getattr(settings, name)
        if isinstance(value, SecretStr):
            values[name] = value.get_secret_value()
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def private_bytes(path: Path, limit: int = MAX_CONFIGURATION) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RecoveryError("Private recovery input is missing or is not a regular file.")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise RecoveryError("Private recovery input must deny group and other access.")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if not data or len(data) > limit:
        raise RecoveryError("Private recovery input is empty or exceeds the size limit.")
    return data


def write_private(path: Path, data: bytes) -> None:
    if os.name != "nt" and path.parent.stat().st_mode & 0o077:
        raise RecoveryError("Recovery output directory must deny group and other access.")
    # O_EXCL also refuses existing symlinks; never replace an operator's configuration.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def outside_backup(backup: Path, *paths: Path) -> None:
    if any(path.resolve().is_relative_to(backup.resolve()) for path in paths):
        raise RecoveryError(
            "Keep private configuration, its encrypted export and key outside the data backup."
        )


def recovery_key(path: Path) -> bytes:
    value = private_bytes(path).strip()
    if not re.fullmatch(rb"[0-9a-f]{64}", value):
        raise RecoveryError("Recovery key must contain 32 random bytes encoded as lowercase hex.")
    return bytes.fromhex(value.decode("ascii"))


def check_provider_keys(session: Session, settings: Settings) -> int:
    keys = list(session.scalars(select(AccountProviderKey)))
    if keys and not re.fullmatch(r"[0-9a-f]{64}", settings.provider_vault_key.get_secret_value()):
        raise RecoveryError(
            "Provider vault key is missing or malformed; "
            "restore the matching private configuration."
        )
    for key in keys:
        try:
            decrypt_key(key, settings)
        except HTTPException:
            raise RecoveryError(
                "Stored provider keys cannot be decrypted with this configuration."
            ) from None
    return len(keys)


def create_inventory(backup: Path, environment_file: Path, settings: Settings) -> Inventory:
    outside_backup(backup, environment_file)
    private_bytes(environment_file)
    database = Database(settings)
    try:
        if not database.ready():
            raise RecoveryError("Database migration head does not match this API release.")
        with database.sessions.begin() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            check_provider_keys(session, settings)
    finally:
        database.close()
    release = json.loads((backup / "manifest.json").read_bytes())
    if release.get("migration_head") != migration_head():
        raise RecoveryError("Backup release metadata does not match the database migration head.")
    return Inventory(
        created_at=datetime.now(UTC).isoformat(),
        configuration_sha256=digest(environment_file),
        settings_sha256=settings_digest(settings),
        migration_head=migration_head(),
        files={name: digest(backup / name) for name in DATA_FILES},
    )


def read_inventory(backup: Path) -> Inventory:
    path = backup / "recovery.json"
    if path.is_symlink() or path.stat().st_size > MAX_CONFIGURATION:
        raise RecoveryError("Recovery inventory is invalid.")
    inventory = Inventory.model_validate_json(path.read_bytes())
    if set(inventory.files) != set(DATA_FILES) or any(
        digest(backup / name) != expected for name, expected in inventory.files.items()
    ):
        raise RecoveryError(
            "Data backup integrity check failed; use the matching unmodified backup."
        )
    return inventory


def seal_configuration(backup: Path, environment_file: Path, key_file: Path, output: Path) -> None:
    outside_backup(backup, environment_file, key_file, output)
    inventory = read_inventory(backup)
    data = private_bytes(environment_file)
    if hashlib.sha256(data).hexdigest() != inventory.configuration_sha256:
        raise RecoveryError("Configuration does not match this data backup.")
    payload = json.dumps(
        {"inventory": inventory.model_dump(), "configuration": base64.b64encode(data).decode()}
    ).encode()
    nonce = os.urandom(12)
    encrypted = AESGCM(recovery_key(key_file)).encrypt(nonce, payload, AAD)
    write_private(output, AAD + b"\n" + nonce + encrypted)


def unseal_configuration(backup: Path, encrypted_file: Path, key_file: Path, output: Path) -> None:
    outside_backup(backup, encrypted_file, key_file, output)
    inventory = read_inventory(backup)
    encrypted = private_bytes(encrypted_file, MAX_CONFIGURATION * 2)
    try:
        prefix = AAD + b"\n"
        if not encrypted.startswith(prefix):
            raise ValueError
        content = encrypted[len(prefix) :]
        data = AESGCM(recovery_key(key_file)).decrypt(content[:12], content[12:], AAD)
        payload = json.loads(data)
        if Inventory.model_validate(payload["inventory"]) != inventory:
            raise RecoveryError("Configuration export belongs to a different data backup.")
        configuration = base64.b64decode(payload["configuration"], validate=True)
        if hashlib.sha256(configuration).hexdigest() != inventory.configuration_sha256:
            raise ValueError
    except (ValueError, InvalidTag, KeyError, TypeError):
        raise RecoveryError(
            "Configuration recovery failed: wrong key or damaged encrypted export."
        ) from None
    write_private(output, configuration)


def verify_recovery(settings: Settings) -> dict[str, int | str]:
    """Verify restored state before reopening traffic, without changing durable state."""
    database = Database(settings)
    counts: dict[str, int | str] = {"migration_head": migration_head()}
    try:
        if not database.ready():
            raise RecoveryError("Database migration head does not match this API release.")
        if not (settings.artifact_directory / "v1").is_dir():
            raise RecoveryError("Restored artifact directory is missing.")
        store = LocalArtifactStore(settings.artifact_directory)
        with database.sessions.begin() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            artifacts = 0
            for artifact in session.scalars(select(Artifact).execution_options(yield_per=100)):
                store.read(artifact.id, artifact.checksum, artifact.size_bytes)
                artifacts += 1
            counts["artifacts"] = artifacts
            checkpoints = 0
            for checkpoint in session.scalars(select(Checkpoint).execution_options(yield_per=100)):
                checkpoint_artifact = (
                    session.get(Artifact, checkpoint.artifact_id)
                    if checkpoint.artifact_id
                    else None
                )
                if (
                    checkpoint_artifact is None
                    or checkpoint_artifact.kind != "workflow_state"
                    or checkpoint_artifact.job_id != checkpoint.job_id
                    or checkpoint_artifact.attempt_id != checkpoint.attempt_id
                    or checkpoint.artifact_ref != "artifact:" + str(checkpoint_artifact.id)
                    or checkpoint.checksum != checkpoint_artifact.checksum
                    or checkpoint.format_version != 1
                ):
                    raise RecoveryError(
                        "Checkpoint metadata is inconsistent or requires legacy reference review."
                    )
                state = WorkflowState.model_validate_json(
                    store.read(
                        checkpoint_artifact.id,
                        checkpoint_artifact.checksum,
                        checkpoint_artifact.size_bytes,
                    )
                )
                if (
                    state.job_id != checkpoint.job_id
                    or state.attempt_id != checkpoint.attempt_id
                    or state.checkpoint_version != checkpoint.version
                ):
                    raise RecoveryError("Restored checkpoint identity failed validation.")
                job = session.get(Job, checkpoint.job_id)
                agent = session.get(Agent, job.agent_id) if job and job.agent_id else None
                attempt = session.get(Attempt, checkpoint.attempt_id)
                if (
                    job is None
                    or agent is None
                    or attempt is None
                    or state.fencing_token != attempt.fencing_token
                ):
                    raise RecoveryError("Restored checkpoint execution metadata failed validation.")
                state_for(WorkflowAssignment(agent=agent_view(agent), state=state), state)
                for committed in state.completed:
                    load_artifact(session, store, job, committed.output)
                checkpoints += 1
            counts["checkpoints"] = checkpoints
            workflows = 0
            for run in session.scalars(select(WorkflowRun).execution_options(yield_per=100)):
                job = session.get(Job, run.job_id)
                attempt = (
                    session.scalar(
                        select(Attempt).where(
                            Attempt.job_id == run.job_id, Attempt.number == job.attempt_count
                        )
                    )
                    if job
                    else None
                )
                if run.checkpoint_version:
                    if job is None or attempt is None:
                        raise RecoveryError("Restored workflow attempt is missing.")
                    workflow_assignment(session, store, job, attempt)
                workflows += 1
            counts["workflows"] = workflows
            counts["provider_keys"] = check_provider_keys(session, settings)
            # A restored snapshot must not re-authorize an old still-live worker lease.
            live_lease = session.scalar(
                select(Attempt.id)
                .where(
                    Attempt.status.in_(("ASSIGNED", "RUNNING")),
                    Attempt.lease_expires_at > datetime.now(UTC),
                )
                .limit(1)
            )
            if live_lease is not None:
                raise RecoveryError(
                    "Restored worker leases have not expired; keep workers and traffic blocked."
                )
        return counts
    except ArtifactError:
        raise RecoveryError(
            "Restored artifact is missing or failed integrity validation."
        ) from None
    except (HTTPException, ValidationError, WorkflowError):
        raise RecoveryError(
            "Restored checkpoint or workflow failed integrity validation."
        ) from None
    finally:
        database.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new_key = commands.add_parser("new-key")
    new_key.add_argument("--key-file", type=Path, required=True)
    inventory_parser = commands.add_parser("inventory")
    inventory_parser.add_argument("--backup", type=Path, required=True)
    inventory_parser.add_argument("--environment-file", type=Path, required=True)
    for name in ("seal-config", "unseal-config"):
        command = commands.add_parser(name)
        command.add_argument("--backup", type=Path, required=True)
        command.add_argument("--key-file", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--input", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--backup", type=Path, required=True)
    verify.add_argument("--environment-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "new-key":
            write_private(args.key_file, (secrets.token_hex(32) + "\n").encode())
        elif args.command == "inventory":
            print(
                create_inventory(args.backup, args.environment_file, Settings()).model_dump_json(
                    indent=2
                )
            )
            return 0
        elif args.command == "seal-config":
            seal_configuration(args.backup, args.input, args.key_file, args.output)
        elif args.command == "unseal-config":
            unseal_configuration(args.backup, args.input, args.key_file, args.output)
        else:
            inventory = read_inventory(args.backup)
            private_bytes(args.environment_file)
            if digest(args.environment_file) != inventory.configuration_sha256:
                raise RecoveryError("Configuration does not match this data backup.")
            settings = Settings()
            verified = verify_recovery(settings)
            if settings_digest(settings) != inventory.settings_sha256:
                raise RecoveryError(
                    "Effective API configuration does not match this data backup; "
                    "check recovered settings and Compose overrides."
                )
            print(json.dumps(verified, sort_keys=True))
            return 0
        print("Recovery operation completed; private contents were not printed.")
        return 0
    except RecoveryError as error:
        print(str(error), file=sys.stderr)
    except FileExistsError:
        print("Recovery output already exists; refusing to overwrite.", file=sys.stderr)
    except (OSError, ValueError, SQLAlchemyError, KeyError, TypeError):
        print(
            "Recovery check failed; verify private inputs, storage and database availability.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
