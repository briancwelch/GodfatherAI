"""Real Git snapshots and optional real container tests; originals are preserved."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from godfather_agent_runtime import WorkflowError
from godfather_contracts import ModelDeployment
from godfather_contracts.agents import WorkflowInput, WorkflowStep
from godfather_contracts.coding import CodingRepository, FileEdit
from godfather_model_gateway import Chunk
from godfather_model_gateway import Provider as ProviderProtocol
from godfather_worker.coding import execute, local_engine, sandbox, search_files, snapshot
from pydantic import ValidationError


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/etc/passwd",
        "C:/secret",
        "a/../../b",
        ".git/config",
        ".env",
        "a\\..\\b",
        "NUL",
        "a/CON",
        "a:stream",
        "a/../b",
    ],
)
def test_coding_paths_cannot_escape_workspace(path: str) -> None:
    with pytest.raises(ValidationError):
        FileEdit(path=path, content="blocked")


def repository(tmp_path: Path, image: str = "python@sha256:" + "a" * 64) -> CodingRepository:
    source = tmp_path / "repo"
    source.mkdir()
    (source / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (source / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\nclass TestAdd(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
    )
    (source / ".env").write_text("fixture-private-value")
    for args in (
        ["init", "--quiet"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(
            ["git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source), *args],
            check=True,
            capture_output=True,
        )
    return CodingRepository(
        id=uuid4(),
        path=source,
        image=image,
        allowed_user_ids=[uuid4()],
        allowed_workspace_ids=[uuid4()],
        files=["*.py"],
        commands=[["python", "-m", "unittest", "-v"]],
    )


@pytest.mark.skipif(
    shutil.which("git") is None, reason="Git snapshot acceptance runs on native worker hosts"
)
def test_snapshot_contains_only_committed_approved_files(tmp_path: Path) -> None:
    config = repository(tmp_path)
    (config.path / "uncommitted.py").write_text("not included")
    target = tmp_path / "copy"
    target.mkdir()
    revision, files = asyncio.run(snapshot(config, target))
    assert len(revision) == 40 and set(files) == {"calc.py", "test_calc.py"}
    assert not (target / ".env").exists() and not (target / ".git").exists()


def test_remote_docker_endpoints_are_refused_without_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "ssh://unapproved.invalid")
    with pytest.raises(WorkflowError, match="tool_permission"):
        asyncio.run(local_engine(tmp_path))


def test_code_search_returns_bounded_literal_matches_from_the_snapshot() -> None:
    matches = search_files(
        {"calc.py": "def add(a,b):\n    return a+b\n", "other.py": "unchanged\n"}, ["add"]
    )
    assert matches == [{"path": "calc.py", "line": 1, "text": "def add(a,b):"}]
    assert len(search_files({"many.py": "needle\n" * 1000}, ["needle"])) == 32


@pytest.mark.skipif(shutil.which("git") is None, reason="Requires local Git")
def test_approved_project_handles_git_ownership_without_global_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = repository(tmp_path)
    target = tmp_path / "snapshot"
    target.mkdir()
    spawn = asyncio.create_subprocess_exec

    async def different_owner(*args: str, **kwargs: Any) -> asyncio.subprocess.Process:
        kwargs["env"]["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"
        return await spawn(*args, **kwargs)

    monkeypatch.setattr("godfather_worker.coding.asyncio.create_subprocess_exec", different_owner)
    revision, files = asyncio.run(snapshot(config, target))
    assert len(revision) == 40 and set(files) == {"calc.py", "test_calc.py"}
    assert not (target / ".git").exists() and not (target / ".env").exists()


def test_real_container_has_no_host_secrets_or_writable_host_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = os.getenv("GODFATHER_CODING_IMAGE")
    if not image:
        pytest.skip("requires explicit existing pinned Linux container image")
    monkeypatch.setenv("GODFATHER_TEST_PROVIDER_SECRET", "fixture-host-secret")
    config = repository(tmp_path, image)
    target = tmp_path / "snapshot"
    target.mkdir()
    asyncio.run(snapshot(config, target))
    probe = """
import errno, os, pathlib
assert 'GODFATHER_TEST_PROVIDER_SECRET' not in os.environ
assert not pathlib.Path('/workspace/.git').exists()
assert not pathlib.Path('/workspace/.env').exists()
assert len(pathlib.Path('/proc/net/route').read_text().splitlines()) <= 1
pathlib.Path('/workspace/disposable.txt').write_text('temporary')
try:
    pathlib.Path('/input/escape.txt').write_text('blocked')
except OSError as error:
    assert error.errno == errno.EROFS
else:
    raise AssertionError('host mount writable')
"""
    result = asyncio.run(sandbox(target, config, ["python", "-c", probe], 30))
    assert result.exit_code == 0, result.output
    assert not (target / "disposable.txt").exists() and not (target / "escape.txt").exists()


def test_real_container_coding_diff_and_test_report(tmp_path: Path) -> None:
    image = os.getenv("GODFATHER_CODING_IMAGE")
    if not image:
        pytest.skip("requires explicit existing pinned Linux container image")
    config = repository(tmp_path, image)

    class Provider:
        async def infer(self, model: str, request: object) -> Any:
            yield Chunk(
                text=json.dumps(
                    {
                        "summary": "Correct addition",
                        "edits": [
                            {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"}
                        ],
                    }
                ),
                done=True,
            )

    result, _ = asyncio.run(
        execute(
            config,
            WorkflowInput(instruction="Fix addition"),
            WorkflowStep(
                id="coding", kind="coding", instruction="Repair the code", output_schema="coding"
            ),
            cast(ProviderProtocol, Provider()),
            ModelDeployment(provider_id="fixture", provider="ollama", identifier="fixture"),
        )
    )
    assert result.tests[0].exit_code == 0 and "OK" in result.tests[0].output
    assert "return a + b" in result.diff and result.files_changed == ["calc.py"]
    assert "a - b" in (config.path / "calc.py").read_text()
    assert "fixture-private-value" not in result.model_dump_json()
