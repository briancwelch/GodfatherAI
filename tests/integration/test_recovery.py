"""Real dump/restore into fresh disposable storage; no existing Compose project is used."""

import json
import os
import shutil
import socket
import subprocess
import tarfile
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from godfather_api import recovery
from godfather_api.account_providers import decrypt_key, encrypt_key
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.migrations import migration_config, migration_head
from godfather_api.models import AccountProviderKey, Artifact, Attempt, Checkpoint
from pydantic import SecretStr
from sqlalchemy import select, text

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_workflows import (
    PLAN,
    USAGE,
    create,
    enable,
    first_checkpoint,
    run_worker,
    step,
    submit,
)

pytestmark = pytest.mark.integration


class DisposablePostgres:
    def __init__(self) -> None:
        self.docker = shutil.which("docker")
        if self.docker is None:
            pytest.fail("Docker is required for the explicitly requested recovery drill")
        image = os.getenv("GODFATHER_RECOVERY_POSTGRES_IMAGE", "postgres:17.11-bookworm")
        self.image = self.run("image", "inspect", image, "--format", "{{.Id}}").decode().strip()
        assert self.image.startswith("sha256:")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.container_id = ""

    def run(self, *args: str, data: bytes | None = None) -> bytes:
        assert self.docker is not None
        result = subprocess.run(
            [self.docker, *args], input=data, capture_output=True, timeout=90, check=False
        )
        if result.returncode:
            # Never render command/environment/SQL inputs or captured process output.
            pytest.fail("Disposable recovery Docker operation failed (output suppressed)")
        return result.stdout

    def start(self) -> None:
        assert not self.container_id
        name = "godfather-recovery-test-" + uuid4().hex[:12]
        self.container_id = (
            self.run(
                "run",
                "--pull=never",
                "--rm",
                "--detach",
                "--name",
                name,
                "--env",
                "POSTGRES_DB=godfather_test",
                "--env",
                "POSTGRES_USER=godfather",
                "--env",
                "POSTGRES_PASSWORD=recovery-only-disposable-password",
                "--publish",
                f"127.0.0.1:{self.port}:5432",
                "--tmpfs",
                "/var/lib/postgresql/data",
                self.image,
            )
            .decode()
            .strip()
        )
        self.run(
            "exec",
            self.container_id,
            "bash",
            "-c",
            "for attempt in {1..150}; do pg_isready -h 127.0.0.1 -U godfather -d godfather_test "
            "&& exit 0; sleep 0.1; done; exit 1",
        )

    def stop(self) -> None:
        if self.container_id:
            # Act only on the exact generated container ID, never an existing project/volume.
            self.run("stop", "--time", "1", self.container_id)
            self.container_id = ""


@pytest.fixture
def postgres() -> Iterator[DisposablePostgres]:
    if os.getenv("GODFATHER_RUN_RECOVERY") != "1":
        pytest.skip("requires explicit opt-in to create disposable Docker recovery containers")
    instance = DisposablePostgres()
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()


def test_complete_restore_keys_checkpoints_and_downtime_fencing(
    postgres: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    artifacts = state / "artifacts"
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    environment = private / "production.env"
    vault_key = "ab" * 32
    provider_key = "synthetic-provider-key-never-contact-a-provider"
    configuration = {
        "GODFATHER_ENVIRONMENT": "test",
        "GODFATHER_DATABASE_HOST": "127.0.0.1",
        "GODFATHER_DATABASE_PORT": str(postgres.port),
        "GODFATHER_DATABASE_NAME": "godfather_test",
        "GODFATHER_DATABASE_USER": "godfather",
        "GODFATHER_DATABASE_PASSWORD": "recovery-only-disposable-password",
        "GODFATHER_ARTIFACT_DIRECTORY": str(artifacts).replace("\\", "/"),
        "GODFATHER_HEALTH_MONITOR_ENABLED": "false",
        "GODFATHER_TEST_LEGACY_CREDENTIALS": "true",
        "GODFATHER_PROVIDER_VAULT_KEY": vault_key,
        "GODFATHER_GOOGLE_CLIENT_ID": "nonfunctional-recovery-test",
        "GODFATHER_GOOGLE_CLIENT_SECRET": "synthetic-oauth-secret",
    }
    for name, value in configuration.items():
        monkeypatch.setenv(name, value)
    recovery.write_private(
        environment, "".join(f"{k}={v}\n" for k, v in configuration.items()).encode()
    )
    settings = Settings()
    command.upgrade(migration_config(), "head")
    database = Database(settings)
    try:
        with TestClient(create_app(settings)) as client:
            harness = Harness(database, client)
            enable(harness)
            enable(harness, 1)
            job = submit(harness, create(harness))
            harness.tick()
            original = harness.poll()
            assert original is not None
            checkpoint = first_checkpoint(harness, original)
            step(harness, original, "describe", 1)  # Uncommitted at the backup point.
            with database.sessions.begin() as session:
                session.add(
                    AccountProviderKey(
                        owner_id=UUID(harness.admin["owner_id"]),
                        provider="openai",
                        encrypted_key=encrypt_key(
                            provider_key, UUID(harness.admin["owner_id"]), "openai", settings
                        ),
                        allowed_node_ids=[harness.workers[0]["credential_id"]],
                    )
                )
                attempt = session.get(Attempt, UUID(original["attempt_id"]))
                assert attempt is not None
                downtime_end = attempt.lease_expires_at + timedelta(seconds=5)
        # API lifespan has ended; no application writer runs during the paired snapshot.
        backup = tmp_path / "data-backup"
        backup.mkdir(mode=0o700)
        dump = postgres.run(
            "exec",
            postgres.container_id,
            "pg_dump",
            "-U",
            "godfather",
            "-d",
            "godfather_test",
            "-Fc",
        )
        (backup / "database.dump").write_bytes(dump)
        with tarfile.open(backup / "artifacts.tar.gz", "w:gz") as archive:
            archive.add(artifacts, arcname="artifacts")
        (backup / "release.env").write_text("API_IMAGE=synthetic-matching-release\n")
        (backup / "manifest.json").write_text(json.dumps({"migration_head": migration_head()}))
        inventory = recovery.create_inventory(backup, environment, settings)
        with pytest.raises(recovery.RecoveryError, match="cannot be decrypted"):
            recovery.create_inventory(
                backup,
                environment,
                settings.model_copy(update={"provider_vault_key": SecretStr("ef" * 32)}),
            )
        (backup / "recovery.json").write_text(inventory.model_dump_json())
        key = private / "recovery.key"
        recovery.write_private(key, b"cd" * 32)
        encrypted = private / "configuration.enc"
        recovery.seal_configuration(backup, environment, key, encrypted)
    finally:
        database.close()

    # Discard the entire source database; source files remain only as comparison evidence.
    postgres.stop()
    for name in configuration:
        monkeypatch.delenv(name)
    environment.rename(private / "source.env")
    artifacts.rename(state / "source-artifacts")
    postgres.start()
    postgres.run(
        "exec",
        "-i",
        postgres.container_id,
        "pg_restore",
        "-U",
        "godfather",
        "-d",
        "godfather_test",
        "--exit-on-error",
        "--no-owner",
        data=dump,
    )
    recovery.unseal_configuration(backup, encrypted, key, environment)
    assert recovery.digest(environment) == inventory.configuration_sha256
    # Load the recovered file, rather than retaining the original process's secrets.
    recovered_settings = Settings(_env_file=environment)
    for name in configuration:
        value = getattr(recovered_settings, name.removeprefix("GODFATHER_").lower())
        monkeypatch.setenv(
            name, value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        )
    with tarfile.open(backup / "artifacts.tar.gz", "r:gz") as archive:
        archive.extractall(state, filter="data")
    database = Database(Settings())
    try:
        assert database.ready()
        with pytest.raises(recovery.RecoveryError, match="leases have not expired"):
            recovery.verify_recovery(Settings())
        clock = Mock(wraps=datetime)
        clock.now.return_value = downtime_end
        # Advance lease/health clocks; step-duration checks retain PostgreSQL's wall clock.
        for module in ("recovery", "nodes", "jobs", "scheduler"):
            monkeypatch.setattr(f"godfather_api.{module}.datetime", clock)
        verified = recovery.verify_recovery(Settings())
        assert verified == {
            "migration_head": migration_head(),
            "artifacts": 2,
            "checkpoints": 1,
            "workflows": 1,
            "provider_keys": 1,
        }
        # Read-only verification must not fence/renew attempts or reveal decrypted values.
        with database.sessions() as session:
            attempt = session.get(Attempt, UUID(original["attempt_id"]))
            assert attempt is not None and attempt.status == "RUNNING"
            assert attempt.fencing_token == original["fencing_token"]
            stored_key = session.scalar(select(AccountProviderKey))
            assert stored_key is not None and decrypt_key(stored_key, Settings()) == provider_key
            assert stored_key.allowed_node_ids == [harness.workers[0]["credential_id"]]
        for bad, message in (("", "missing or malformed"), ("ef" * 32, "cannot be decrypted")):
            with pytest.raises(recovery.RecoveryError, match=message) as failure:
                recovery.verify_recovery(
                    Settings().model_copy(update={"provider_vault_key": SecretStr(bad)})
                )
            assert provider_key not in str(failure.value) and vault_key not in str(failure.value)
            with monkeypatch.context() as missing_or_wrong:
                missing_or_wrong.setenv("GODFATHER_PROVIDER_VAULT_KEY", bad)
                assert (
                    recovery.main(
                        ["verify", "--backup", str(backup), "--environment-file", str(environment)]
                    )
                    == 1
                )
                output = capsys.readouterr()
                assert message in output.err
                assert provider_key not in output.out + output.err
                assert vault_key not in output.out + output.err
        with monkeypatch.context() as override:
            override.setenv("GODFATHER_SESSION_SECONDS", "3600")
            assert (
                recovery.main(
                    ["verify", "--backup", str(backup), "--environment-file", str(environment)]
                )
                == 1
            )
            assert "Effective API configuration does not match" in capsys.readouterr().err
        assert (
            recovery.main(
                ["verify", "--backup", str(backup), "--environment-file", str(environment)]
            )
            == 0
        )
        output = capsys.readouterr()
        assert (
            provider_key not in output.out + output.err and vault_key not in output.out + output.err
        )
        with TestClient(create_app(Settings())) as restored:
            harness.client, harness.database = restored, database
            # Restoring the database must not supply missing local worker consent.
            for index in (0, 1):
                worker = harness.workers[index]
                response = restored.post(
                    f"/api/v1/workers/{worker['credential_id']}/account-providers",
                    headers=headers(worker),
                    json={"session_id": str(harness.registrations[index].session_id)},
                )
                assert response.status_code == 403 and provider_key not in response.text
            # The restored lease is expired even before the scheduler performs recovery.
            harness.report(original, "renew", expected=409)
            harness.report(
                original,
                "complete",
                expected=409,
                result={
                    "workflow_id": checkpoint["workflow_id"],
                    "workflow_version": checkpoint["workflow_version"],
                    "agent_id": checkpoint["agent_id"],
                    "agent_version": checkpoint["agent_version"],
                    "checkpoint_version": 1,
                    "completed_steps": ["plan"],
                    "final_output": checkpoint["context"]["plan"],
                },
            )
            step(
                harness,
                original,
                "describe",
                1,
                "checkpoint",
                expected=409,
                output=PLAN,
                usage=USAGE,
            )
            registration = harness.registrations[1]
            response = restored.post(
                "/api/v1/workers/register",
                headers=headers(harness.workers[1]),
                json=registration.model_dump(mode="json"),
            )
            assert response.status_code == 200, response.text
            harness.tick(downtime_end)
            harness.tick(downtime_end + timedelta(seconds=2))
            replacement = harness.poll(1)
            assert replacement is not None
            assert replacement["fencing_token"] > original["fencing_token"]
            assert replacement["workflow"]["state"]["context"] == checkpoint["context"]
            provider = run_worker(harness, replacement, index=1)
            assert len(provider.calls) == 1  # The committed model call was not repeated.
            harness.report(original, "renew", expected=409)
            assert harness.get(job["id"])["status"] == "COMPLETED"
            assert recovery.verify_recovery(Settings())["checkpoints"] == 3
        # Corruption/head mismatch must fail independently of provider-key validity.
        with database.sessions() as session:
            artifact = session.scalar(select(Artifact))
            assert artifact is not None
            artifact_path = artifacts / "v1" / (artifact.id.hex + ".json")
            original_bytes = artifact_path.read_bytes()
        artifact_path.write_bytes(b"corrupted")
        with pytest.raises(recovery.RecoveryError, match="artifact.*integrity"):
            recovery.verify_recovery(Settings())
        artifact_path.write_bytes(original_bytes)
        with database.sessions.begin() as session:
            checkpoint_row = session.scalar(select(Checkpoint))
            assert checkpoint_row is not None
            original_checksum, checkpoint_id = checkpoint_row.checksum, checkpoint_row.id
            checkpoint_row.checksum = "0" * 64
        with pytest.raises(recovery.RecoveryError, match="Checkpoint metadata"):
            recovery.verify_recovery(Settings())
        with database.sessions.begin() as session:
            checkpoint_row = session.get(Checkpoint, checkpoint_id)
            assert checkpoint_row is not None
            checkpoint_row.checksum = original_checksum
            session.execute(text("UPDATE alembic_version SET version_num = 'wrong_recovery_head'"))
        with pytest.raises(recovery.RecoveryError, match="migration head"):
            recovery.verify_recovery(Settings())
    finally:
        database.close()
