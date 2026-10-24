"""Desktop event tests run without a display, account, network, or installer."""

import queue
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

pytest.importorskip("tkinter", exc_type=ImportError)

from godfather_worker.desktop import Contribution  # noqa: E402
from godfather_worker.desktop_app import Application  # noqa: E402
from godfather_worker.desktop_theme import Preferences  # noqa: E402


def application(tmp_path: Path) -> Any:
    app = object.__new__(Application)
    app.root = Mock()
    app.folder = tmp_path
    app.identity = {"origin": "https://coordinator.invalid"}
    app.controller = Mock(origin="https://coordinator.invalid")
    app.address, app.status, app.connection_state = Mock(), Mock(), Mock()
    app.connection_badge, app.secure_label, app.footer_status = Mock(), Mock(), Mock()
    app.update_info = None
    app.update_pending = None
    app.update_busy = app.update_checking = app.local_setup_busy = False
    app.build_version = "0.9.0-rc.2"
    app.update_progress, app.update_status = Mock(), Mock()
    app.preferences = Preferences()
    app.update_timer = None
    app.events = queue.Queue()
    app.destroyed, app.closing = False, False
    app.tray = None
    app.settings = Contribution()
    app.models = []
    app.background = Mock()  # type: ignore[method-assign]
    return app


@pytest.mark.parametrize("failure", [False, True])
def test_check_update_shows_progress_immediately_and_finishes_on_success_or_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    app = application(tmp_path)
    available = Mock(side_effect=OSError("offline")) if failure else Mock(return_value=None)
    monkeypatch.setattr("godfather_worker.updates.available_update", available)
    app.check_updates()
    app.update_status.set.assert_called_with("Checking for updates…")
    app.update_progress.start.assert_called_once()
    assert app.update_checking
    app.check_updates()  # No duplicate HTTP check.
    app.background.assert_called_once()
    app.background.call_args.args[0]()
    app.pump()
    assert not app.update_checking
    app.update_progress.stop.assert_called_once()
    app.update_progress.pack_forget.assert_called_once()
    assert ("failed" if failure else "up to date") in app.update_status.set.call_args.args[0]


@pytest.mark.parametrize(
    "identity,build", [(None, "0.9.0-rc.2"), ({"origin": "https://coordinator.invalid"}, None)]
)
def test_update_ineligible_state_explains_instead_of_silently_returning(
    tmp_path: Path, identity: dict[str, str] | None, build: str | None
) -> None:
    app = application(tmp_path)
    app.identity, app.build_version = identity, build
    app.check_updates()
    app.update_status.set.assert_called_once()
    app.background.assert_not_called()
    app.update_progress.start.assert_not_called()


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8000", "https://coordinator.invalid"])
def test_lock_requires_confirmed_connection_and_https_and_clears_on_loss(
    tmp_path: Path, origin: str
) -> None:
    app = application(tmp_path)
    app.controller.origin = origin
    app.set_connection_state("CONNECTING")
    app.secure_label.pack.assert_not_called()
    app.event("worker.registered", available_models=["fixture"])
    app.pump()
    assert app.secure_label.pack.called is origin.startswith("https:")
    app.secure_label.reset_mock()
    app.event("worker.coordinator_unavailable")
    app.pump()
    app.secure_label.pack_forget.assert_called_once()
    app.secure_label.pack.assert_not_called()


@pytest.mark.parametrize(
    "state", ["PAUSED", "DISABLED", "ACCESS REFUSED", "DISCONNECTED", "WAITING FOR SESSION"]
)
def test_unconfirmed_states_never_show_secure_lock(tmp_path: Path, state: str) -> None:
    app = application(tmp_path)
    app.set_connection_state(state)
    app.secure_label.pack.assert_not_called()
    app.secure_label.pack_forget.assert_called_once()


def test_scan_load_is_owner_initiated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from godfather_worker.simulated import profile

    app = application(tmp_path)
    app.store = Mock(read=Mock(return_value=None))
    discover = Mock(return_value=profile("LA-01"))
    scanner = Mock()
    monkeypatch.setattr("godfather_worker.desktop_app.discover", discover)
    monkeypatch.setattr("godfather_worker.desktop_app.scan", scanner)
    monkeypatch.setattr("godfather_worker.desktop_app.login_startup_enabled", lambda: False)
    app.load()
    discover.assert_called_once_with(include_models=False)
    scanner.assert_not_called()


def test_resume_reenables_locally_approved_group_participation(tmp_path: Path) -> None:
    app = application(tmp_path)
    app.shared_inference = Mock(suspended=True)
    app.start = Mock()
    app.resume()
    assert app.shared_inference.suspended is False
    app.start.assert_called_once()
    app.shared_inference.refresh.assert_called_once()


def test_shared_engine_cleanup_callbacks_run_while_window_is_closing(tmp_path: Path) -> None:
    app = application(tmp_path)
    app.closing = True
    cleanup, unrelated = Mock(), Mock()
    app.event("shared_update", apply=cleanup)
    app.event("project_update", apply=unrelated)
    app.pump()
    cleanup.assert_called_once()
    unrelated.assert_not_called()


def test_scan_results_never_enable_servers_until_owner_selects_use(tmp_path: Path) -> None:
    from godfather_model_gateway import ProviderConfig
    from godfather_worker.local_model_scan import ScanResult

    app = application(tmp_path)
    existing = ProviderConfig(
        id="old-local", provider="openai_compatible", url="http://127.0.0.1:9000/v1"
    )
    found = ProviderConfig(
        id="new-local",
        provider="openai_compatible",
        url="http://127.0.0.1:1234/v1",
        discovery_models=["fixture"],
    )
    app.settings = Contribution(local_providers=[existing])
    app.scan_button, app.model_scan_button, app.cancel_scan_button = Mock(), Mock(), Mock()
    app.scan_table = Mock()
    app.scan_table.get_children.return_value = []
    app.use_scanned_button, app.scan_status = Mock(), Mock()
    app.apply_settings = Mock()
    app.event("scan_finished", result=ScanResult(providers=[found]))
    app.pump()
    app.apply_settings.assert_not_called()
    app.use_scanned_models()
    saved = app.apply_settings.call_args.args[0]
    assert saved.inference
    assert {p.id for p in saved.local_providers} == {"old-local", "new-local"}
    enabled = next(p for p in saved.local_providers if p.id == "new-local")
    assert enabled.chat_enabled and enabled.stream_enabled
    assert not saved.model_installation and not saved.account_providers


@pytest.mark.parametrize("replace", [False, True])
def test_enabling_new_servers_at_limit_requires_owner_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replace: bool
) -> None:
    from godfather_model_gateway import ProviderConfig
    from godfather_worker.local_model_scan import ScanResult

    app = application(tmp_path)
    app.settings = Contribution(
        local_providers=[
            ProviderConfig(
                id=f"saved-{port}", provider="openai_compatible", url=f"http://127.0.0.1:{port}/v1"
            )
            for port in range(9000, 9007)
        ]
    )
    app.scan_result = ScanResult(
        providers=[
            ProviderConfig(id="new", provider="openai_compatible", url="http://127.0.0.1:1234/v1")
        ]
    )
    app.scan_busy, app.scan_status = False, Mock()
    app.apply_settings = Mock()
    monkeypatch.setattr(
        "godfather_worker.desktop_app.messagebox.askyesno", Mock(return_value=replace)
    )
    app.use_scanned_models()
    if replace:
        assert [p.id for p in app.apply_settings.call_args.args[0].local_providers] == ["new"]
    else:
        app.apply_settings.assert_not_called()
