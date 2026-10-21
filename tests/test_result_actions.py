"""Actual Git application, with dirty-file protection and no host shell execution."""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from godfather_contracts.coding import CodingOutput, CodingRepository
from godfather_worker.coding import command
from godfather_worker.result_actions import ApplyBlocked, apply_patch

from tests.test_coding import repository


async def noop() -> None:
    pass


def patch_output(config: CodingRepository, revision: str) -> CodingOutput:
    return CodingOutput(
        repository_id=config.id,
        base_commit=revision,
        summary="Correct addition.",
        files_changed=["calc.py"],
        tests=[],
        diff=(
            "diff --git a/calc.py b/calc.py\n--- a/calc.py\n+++ b/calc.py\n"
            "@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
        ),
    )


def setup(tmp_path: Path) -> tuple[CodingRepository, CodingOutput]:
    config = repository(tmp_path).model_copy(update={"allow_apply": True})
    _, head = asyncio.run(command(["git", "rev-parse", "HEAD"], config.path))
    return config, patch_output(config, head.strip())


def test_real_git_apply_preserves_unrelated_edits_and_index(tmp_path: Path) -> None:
    config, output = setup(tmp_path)
    original = (config.path / "test_calc.py").read_bytes()
    (config.path / "test_calc.py").write_bytes(original + b"\n# my work\n")
    result = asyncio.run(apply_patch(config, output, uuid4(), noop))
    assert result == ["calc.py"]
    assert "return a + b" in (config.path / "calc.py").read_text()
    assert (config.path / "test_calc.py").read_bytes() == original + b"\n# my work\n"
    code, _ = asyncio.run(command(["git", "diff", "--cached", "--quiet"], config.path))
    assert code == 0


@pytest.mark.parametrize(
    "dirty",
    [
        "unstaged",
        "staged",
        "base",
        "scope",
        "opt-out",
        "conflict",
        "mismatch",
        "symlink",
        "hidden-edit",
    ],
)
def test_unsafe_application_is_blocked_without_altering_project(tmp_path: Path, dirty: str) -> None:
    config, output = setup(tmp_path)
    target = config.path / "calc.py"
    if dirty in ("unstaged", "staged"):
        target.write_text("my existing work\n")
        if dirty == "staged":
            asyncio.run(command(["git", "add", "calc.py"], config.path))
    elif dirty == "hidden-edit":
        asyncio.run(command(["git", "update-index", "--assume-unchanged", "calc.py"], config.path))
        target.write_text("my hidden edits\n")
    elif dirty == "base":
        output.base_commit = "0" * 40
    elif dirty == "scope":
        config.files = ["test_calc.py"]
    elif dirty == "opt-out":
        config.allow_apply = False
    elif dirty == "conflict":
        output.diff = output.diff.replace("return a - b", "return missing")
    elif dirty == "mismatch":
        output.files_changed = ["test_calc.py"]
    elif dirty == "symlink":
        outside = tmp_path / "outside"
        outside.write_text("private")
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError:
            pytest.skip("host does not permit symlinks")
    before = target.read_bytes()
    with pytest.raises(ApplyBlocked):
        asyncio.run(apply_patch(config, output, uuid4(), noop))
    assert target.read_bytes() == before


def test_authorization_failure_and_local_replay_never_write(tmp_path: Path) -> None:
    config, output = setup(tmp_path)
    original = (config.path / "calc.py").read_bytes()

    async def reject() -> None:
        raise RuntimeError("lease lost")

    with pytest.raises(RuntimeError):
        asyncio.run(apply_patch(config, output, uuid4(), reject))
    assert (config.path / "calc.py").read_bytes() == original
    identifier = uuid4()
    asyncio.run(apply_patch(config, output, identifier, noop))
    with pytest.raises(ApplyBlocked):
        asyncio.run(apply_patch(config, output, identifier, noop))


def test_edits_during_authorization_are_rechecked(tmp_path: Path) -> None:
    config, output = setup(tmp_path)

    async def changed() -> None:
        (config.path / "calc.py").write_text("edited while waiting\n")

    with pytest.raises(ApplyBlocked):
        asyncio.run(apply_patch(config, output, uuid4(), changed))
    assert (config.path / "calc.py").read_text() == "edited while waiting\n"
