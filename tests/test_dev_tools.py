"""Development-runner behavior, including failures and Windows command shims."""

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import dev


def test_checks_stop_at_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock(side_effect=[0, 17])
    monkeypatch.setattr(dev, "run_command", runner)
    assert dev.check() == 17
    assert runner.call_count == 2


def test_checks_run_every_step_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock(return_value=0)
    monkeypatch.setattr(dev, "run_command", runner)
    assert dev.check() == 0
    assert runner.call_count == len(dev.CHECKS)


def test_missing_executable_is_actionable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert dev.run_command(("docker", "info")) == 1
    assert "Missing prerequisite: docker" in capsys.readouterr().out


def test_windows_shim_and_arguments_use_repository_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = r"C:\Program Files\nodejs\npm.CMD"
    monkeypatch.setattr(shutil, "which", lambda _: executable)
    runner = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.chdir(tmp_path)
    assert dev.run_command(("npm", "run", "lint")) == 0
    runner.assert_called_once_with([executable, "run", "lint"], cwd=dev.ROOT, check=False)


def test_spawn_failure_returns_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "/missing/tool")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=OSError("cannot execute")))
    assert dev.run_command(("uv", "--version")) == 1


def test_doctor_continues_after_missing_prerequisite(monkeypatch: pytest.MonkeyPatch) -> None:
    visited: list[Sequence[str]] = []

    def run(command: Sequence[str]) -> int:
        visited.append(command)
        return int(command[0] == "uv")

    monkeypatch.setattr(dev, "run_command", run)
    assert dev.doctor() == 1
    assert visited[-1] == ("docker", "info", "--format", "{{.OSType}}")


def test_doctor_reports_success_when_probes_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "run_command", lambda _: 0)
    assert dev.doctor() == 0
