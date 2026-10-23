"""A missing optional project dependency must not disconnect an otherwise usable worker."""

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from godfather_agent_runtime import WorkflowError
from godfather_contracts import Registration, WorkerAck
from godfather_contracts.coding import CODING_RUNTIME, REPOSITORY_PREFIX, CodingRepository
from godfather_contracts.result_actions import ACTION_RUNTIME, PATCH_RUNTIME, TARGET_PREFIX
from godfather_worker import cli, project_readiness
from godfather_worker.coding_setup import project_config
from godfather_worker.desktop import Contribution, Controller, LimitedClient
from godfather_worker.simulated import profile


def repository(path: Path) -> CodingRepository:
    return project_config(
        name="Example project",
        path=str(path),
        image="sha256:" + "a" * 64,
        owner=uuid4(),
        workspace=uuid4(),
        patterns="*.py",
        test_command="python -m unittest",
    ).model_copy(update={"allow_apply": True})


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("none", None),
        ("git", "git_unavailable"),
        ("context", "docker_unavailable"),
        ("engine", "docker_unavailable"),
        ("windows", "docker_not_linux"),
        ("image", "image_missing"),
        ("image_windows", "image_not_linux"),
        ("engine_stopped", "docker_unavailable"),
    ],
)
def test_dependency_checks_are_read_only_and_return_safe_specific_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected: str | None,
) -> None:
    commands: list[list[str]] = []
    info_calls = 0

    async def command(args: list[str], *_: object) -> tuple[int, str]:
        nonlocal info_calls
        commands.append(args)
        if args[0] == "git":
            if failure == "git":
                raise WorkflowError("tool_permission")
            return 0, "git version fixture"
        if "info" in args:
            info_calls += 1
            if failure == "engine" or (failure == "engine_stopped" and info_calls > 1):
                return 1, "private-engine-output"
            return 0, "windows" if failure == "windows" else "linux"
        if failure in ("image", "engine_stopped"):
            return 1, "private-image-output"
        return 0, "windows" if failure == "image_windows" else "linux"

    async def engine(*_: object) -> str:
        if failure == "context":
            raise WorkflowError("tool_permission")
        return "unix:///fixture.sock"

    monkeypatch.setattr(project_readiness, "command", command)
    monkeypatch.setattr(project_readiness, "local_engine", engine)
    repo = repository(tmp_path)
    assert asyncio.run(project_readiness.project_issue(repo)) == expected
    assert all(args[0] == "git" or "info" in args or "inspect" in args for args in commands)
    if expected:
        message = project_readiness.project_issue_message(repo, expected)
        assert "Pause and Resume" in message
        assert str(tmp_path) not in message and "private-" not in message
    if expected == "image_missing":
        assert repo.image in message and "restore" in message.lower() and "Projects" in message


def test_missing_folder_is_reported_without_running_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = repository(tmp_path).model_copy(update={"path": tmp_path / "missing"})
    command = Mock(side_effect=AssertionError("No process should run"))
    monkeypatch.setattr(project_readiness, "command", command)
    assert asyncio.run(project_readiness.project_issue(repo)) == "folder_missing"
    command.assert_not_called()


@pytest.mark.parametrize("host", ["LV-01", "LA-01", "LA-02"])
@pytest.mark.parametrize("keep_ready_project", [False, True])
def test_desktop_connects_without_advertising_unready_coding_or_apply_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    keep_ready_project: bool,
) -> None:
    bad = repository(tmp_path)
    good = bad.model_copy(update={"id": uuid4(), "image": "sha256:" + "b" * 64})
    missing = True

    async def command(args: list[str], *_: object) -> tuple[int, str]:
        if missing and "inspect" in args and args[-1] == bad.image:
            return 1, "private diagnostic output"
        return 0, "linux"

    async def engine(*_: object) -> str:
        return "unix:///fixture.sock"

    async def models(*_: object) -> list[object]:
        return []

    monkeypatch.setattr(project_readiness, "command", command)
    monkeypatch.setattr(project_readiness, "local_engine", engine)
    monkeypatch.setattr(cli, "discover", lambda: profile(host))
    monkeypatch.setattr(cli, "discover_models", models)
    monkeypatch.setattr("godfather_worker.account_providers.fetch", lambda *_: [])
    registrations: list[Registration] = []

    def register(self: LimitedClient, path: str, payload: Registration) -> WorkerAck:
        assert path == "/api/v1/workers/register"
        registrations.append(payload)
        return WorkerAck(
            node_id=uuid4(),
            state="online",
            connection_status="online",
            heartbeat_interval_seconds=10,
        )

    def poll(self: LimitedClient, path: str, payload: object) -> object:
        assert path.endswith("/jobs/poll")
        controller.stop_event.set()
        return {"assignment": None}

    monkeypatch.setattr(LimitedClient, "post", register)
    monkeypatch.setattr(LimitedClient, "post_document", poll)
    observer = Mock()
    controller = Controller(
        {"kind": "worker", "token": "fixture-secret", "owner_id": str(bad.allowed_user_ids[0])},
        tmp_path / "worker",
        observer,
    )
    settings = Contribution(
        inference=True,
        account_providers=True,
        cloud_images=True,
        repositories=[bad, good] if keep_ready_project else [bad],
    )
    controller.start(settings)
    assert controller.thread is not None
    controller.thread.join(5)
    assert not controller.running and registrations
    for registration in registrations:
        assert [r.id for r in registration.coding_repositories] == (
            [good.id] if keep_ready_project else []
        )
        assert REPOSITORY_PREFIX + str(bad.id) not in registration.runtimes
        assert TARGET_PREFIX + str(bad.id) not in registration.runtimes
        assert "cloud-images-v1" in registration.runtimes
        assert "images.generate" in registration.tool_permissions
        if not keep_ready_project:
            assert not {CODING_RUNTIME, ACTION_RUNTIME, PATCH_RUNTIME}.intersection(
                registration.runtimes
            )
            assert "coding.workspace" not in registration.tool_permissions
        else:
            assert REPOSITORY_PREFIX + str(good.id) in registration.runtimes
            assert TARGET_PREFIX + str(good.id) in registration.runtimes
    saved = Contribution.model_validate_json((controller.folder / "settings.json").read_text())
    assert saved == settings  # Keep the exact project IDs/scopes for a later repair.
    observer.assert_any_call(
        "worker.project_readiness", issues=[{"repository_id": str(bad.id), "code": "image_missing"}]
    )
    assert "worker.registered" in [call.args[0] for call in observer.call_args_list]
    assert "private diagnostic" not in str(observer.call_args_list)
    assert "fixture-secret" not in json.dumps([r.model_dump(mode="json") for r in registrations])
    missing = False
    registrations.clear()
    observer.reset_mock()
    controller.start(saved)
    assert controller.thread is not None
    controller.thread.join(5)
    assert not controller.running and registrations
    assert [r.id for r in registrations[-1].coding_repositories] == [
        r.id for r in saved.repositories
    ]
    observer.assert_any_call("worker.project_readiness", issues=[])
    assert (
        Contribution.model_validate_json((controller.folder / "settings.json").read_text()) == saved
    )


def test_timeout_has_a_bounded_actionable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def timeout(*_: object) -> tuple[int, str]:
        raise TimeoutError

    monkeypatch.setattr(project_readiness, "command", timeout)
    assert asyncio.run(project_readiness.project_issue(repository(tmp_path))) == "check_timeout"


def test_project_warning_survives_heartbeats_and_clears_after_repair(tmp_path: Path) -> None:
    pytest.importorskip("tkinter", exc_type=ImportError)
    import queue

    from godfather_worker.desktop_app import Application

    repo = repository(tmp_path)
    app = object.__new__(Application)
    app.settings = Contribution(repositories=[repo])
    app.project_warning, app.project_notice, app.project_editor = Mock(), Mock(), Mock()
    app.project_issues, app.projects_checked = {}, False
    app.show_project_readiness([{"repository_id": str(repo.id), "code": "image_missing"}])
    warning = app.project_warning.set.call_args.args[0]
    assert repo.name in warning and "image is missing" in warning and "Projects" in warning
    assert "Other enabled work can continue" in warning
    app.events = queue.Queue()
    app.events.put(("worker.heartbeat", {"state": "online"}))
    app.root, app.status, app.set_connection_state = Mock(), Mock(), Mock()  # type: ignore[method-assign]
    app.models, app.tray, app.destroyed = [], None, False
    app.pump()
    app.project_warning.set.assert_called_once_with(warning)
    app.project_notice.pack.assert_called_once()
    app.show_project_readiness([])
    assert not app.project_issues and app.projects_checked
    app.project_warning.set.assert_called_with("")
    app.project_notice.pack_forget.assert_called_once()
