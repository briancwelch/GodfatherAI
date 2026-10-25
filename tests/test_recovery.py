"""Secret recovery is authenticated, snapshot-bound, separate, and non-overwriting."""

import json
import os
from pathlib import Path

import pytest
from godfather_api import recovery


@pytest.fixture
def bundle(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    backup = tmp_path / "data-backup"
    backup.mkdir(mode=0o700)
    for name in recovery.DATA_FILES:
        (backup / name).write_bytes(("synthetic " + name).encode())
    environment = tmp_path / "production.env"
    recovery.write_private(environment, b"SYNTHETIC_SECRET=private-recovery-test\n")
    inventory = recovery.Inventory(
        created_at="2026-10-25T00:00:00Z",
        configuration_sha256=recovery.digest(environment),
        settings_sha256="0" * 64,
        migration_head="test-head",
        files={name: recovery.digest(backup / name) for name in recovery.DATA_FILES},
    )
    (backup / "recovery.json").write_text(inventory.model_dump_json())
    key = tmp_path / "offline.key"
    recovery.write_private(key, b"ab" * 32)
    return backup, environment, key, tmp_path / "configuration.enc"


def test_configuration_round_trip_is_private_and_leaves_data_backup_secret_free(
    bundle: tuple[Path, Path, Path, Path],
) -> None:
    backup, environment, key, encrypted = bundle
    original_files = {file.name: file.read_bytes() for file in backup.iterdir()}
    recovery.seal_configuration(backup, environment, key, encrypted)
    restored = environment.with_name("restored.env")
    recovery.unseal_configuration(backup, encrypted, key, restored)
    assert restored.read_bytes() == environment.read_bytes()
    assert b"private-recovery-test" not in encrypted.read_bytes()
    assert key.read_bytes() not in encrypted.read_bytes()
    assert original_files == {file.name: file.read_bytes() for file in backup.iterdir()}
    assert all(b"private-recovery-test" not in value for value in original_files.values())
    if os.name != "nt":
        assert restored.stat().st_mode & 0o777 == 0o600
        assert encrypted.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("failure", ["wrong_key", "missing_key", "malformed_key", "ciphertext"])
def test_failed_decryption_has_no_output_file_or_secret_disclosure(
    bundle: tuple[Path, Path, Path, Path], failure: str, capsys: pytest.CaptureFixture[str]
) -> None:
    backup, environment, key, encrypted = bundle
    recovery.seal_configuration(backup, environment, key, encrypted)
    if failure == "wrong_key":
        key.write_bytes(b"cd" * 32)
    elif failure == "missing_key":
        key.unlink()
    elif failure == "malformed_key":
        key.write_bytes(b"private-recovery-test")
    else:
        payload = bytearray(encrypted.read_bytes())
        payload[-1] ^= 1
        encrypted.write_bytes(payload)
    output = environment.with_name("restored.env")
    assert (
        recovery.main(
            [
                "unseal-config",
                "--backup",
                str(backup),
                "--input",
                str(encrypted),
                "--key-file",
                str(key),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    capture = capsys.readouterr()
    assert capture.err and not capture.out and not output.exists()
    assert "Traceback" not in capture.err
    assert "private-recovery-test" not in capture.err
    assert "ab" * 32 not in capture.err and "cd" * 32 not in capture.err


def test_configuration_must_match_the_snapshot_and_export_cannot_cross_backups(
    bundle: tuple[Path, Path, Path, Path],
) -> None:
    backup, environment, key, encrypted = bundle
    original = environment.read_bytes()
    environment.write_bytes(original + b"CHANGED=yes\n")
    with pytest.raises(recovery.RecoveryError, match="Configuration does not match"):
        recovery.seal_configuration(backup, environment, key, encrypted)
    assert not encrypted.exists()
    environment.write_bytes(original)
    recovery.seal_configuration(backup, environment, key, encrypted)
    inventory_file = backup / "recovery.json"
    inventory = json.loads(inventory_file.read_text())
    inventory["created_at"] = "different backup"
    inventory_file.write_text(json.dumps(inventory))
    with pytest.raises(recovery.RecoveryError, match="different data backup"):
        recovery.unseal_configuration(backup, encrypted, key, environment.with_name("restored.env"))


@pytest.mark.parametrize("member", recovery.DATA_FILES)
def test_tampered_data_backup_cannot_release_configuration(
    bundle: tuple[Path, Path, Path, Path],
    member: str,
) -> None:
    backup, environment, key, encrypted = bundle
    recovery.seal_configuration(backup, environment, key, encrypted)
    (backup / member).write_bytes(b"corrupted")
    with pytest.raises(recovery.RecoveryError, match="integrity check failed"):
        recovery.unseal_configuration(backup, encrypted, key, environment.with_name("restored.env"))


def test_export_and_key_must_be_separate_from_data_backup_and_never_overwrite(
    bundle: tuple[Path, Path, Path, Path],
) -> None:
    backup, environment, key, encrypted = bundle
    with pytest.raises(recovery.RecoveryError, match="outside the data backup"):
        recovery.seal_configuration(backup, environment, key, backup / "configuration.enc")
    recovery.seal_configuration(backup, environment, key, encrypted)
    with pytest.raises(FileExistsError):
        recovery.unseal_configuration(backup, encrypted, key, environment)
    assert b"private-recovery-test" in environment.read_bytes()
    with pytest.raises(FileExistsError):
        recovery.seal_configuration(backup, environment, key, encrypted)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode check; Windows requires operator ACLs")
def test_shared_private_input_or_output_directory_is_refused(
    bundle: tuple[Path, Path, Path, Path],
) -> None:
    backup, environment, key, encrypted = bundle
    key.chmod(0o644)
    with pytest.raises(recovery.RecoveryError, match="deny group and other"):
        recovery.seal_configuration(backup, environment, key, encrypted)
    key.chmod(0o600)
    public = encrypted.parent / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(recovery.RecoveryError, match="output directory"):
        recovery.seal_configuration(backup, environment, key, public / "configuration.enc")


def test_maximum_configuration_round_trips_and_generated_key_is_not_printed(
    bundle: tuple[Path, Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    backup, environment, key, encrypted = bundle
    key.unlink()
    assert recovery.main(["new-key", "--key-file", str(key)]) == 0
    assert len(recovery.recovery_key(key)) == 32
    assert key.read_text().strip() not in capsys.readouterr().out
    environment.write_bytes(b"a" * recovery.MAX_CONFIGURATION)
    metadata = json.loads((backup / "recovery.json").read_text())
    metadata["configuration_sha256"] = recovery.digest(environment)
    (backup / "recovery.json").write_text(json.dumps(metadata))
    recovery.seal_configuration(backup, environment, key, encrypted)
    output = environment.with_name("restored.env")
    recovery.unseal_configuration(backup, encrypted, key, output)
    assert output.read_bytes() == environment.read_bytes()
