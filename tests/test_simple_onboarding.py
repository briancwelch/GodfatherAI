"""Origin binding and approval polling regression checks without real credentials."""

import json
import socket
import ssl
import threading
from email.message import Message
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler

import pytest
from godfather_worker.client import WorkerClient
from godfather_worker.desktop import Pairing, connection_error, coordinator_origin
from godfather_worker.native_desktop import CredentialStore, login_startup_enabled
from godfather_worker.pairing import await_approval, check_connection


@pytest.mark.parametrize(
    "origin", ["https://example.com", "https://custom.example:8443", "http://127.0.0.1:8000"]
)
def test_operator_supplied_origin(origin: str) -> None:
    assert coordinator_origin(origin + "/") == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/path",
        "https://example.com?secret=x",
        "https://example.com#x",
        "file:///tmp",
        "https://example.com:bad",
    ],
)
def test_reject_ambiguous_or_insecure_origin(origin: str) -> None:
    with pytest.raises(ValueError):
        coordinator_origin(origin)


def test_pairing_binds_saved_identity_without_changing_wire_contract() -> None:
    pairing = Pairing(origin="https://my.example")
    transport, store = Mock(), Mock()
    transport.post_document.return_value = {
        "credential_id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "00000000-0000-0000-0000-000000000002",
    }
    identity = pairing.exchange(store, transport)
    assert identity["origin"] == "https://my.example"
    assert json.loads(store.write.call_args.args[0])["origin"] == "https://my.example"
    assert "origin" not in transport.post_document.call_args.args[1].model_dump()
    assert pairing.browser_url.startswith("https://my.example/worker-enrollment#")
    assert set(pairing.model_dump()) == {"secret", "machine_secret"}


def test_approval_is_automatic_but_never_replays_ambiguous_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = Mock(side_effect=[HTTPError("", 404, "pending", Message(), None), {"token": "test"}])
    monkeypatch.setattr(Pairing, "exchange", exchange)
    cancel = Mock()
    cancel.is_set.return_value = False
    result = await_approval(Pairing(), Mock(), cancel)
    assert result == {"token": "test"}
    cancel.wait.assert_called_once_with(5)
    exchange.side_effect = OSError("response lost")
    exchange.reset_mock()
    with pytest.raises(OSError):
        await_approval(Pairing(), Mock(), cancel)
    assert exchange.call_count == 1


def test_cancelled_pairing_does_not_send_or_store(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = Mock()
    monkeypatch.setattr(Pairing, "exchange", exchange)
    cancel = threading.Event()
    cancel.set()
    assert await_approval(Pairing(), Mock(), cancel) is None
    exchange.assert_not_called()


def test_fresh_host_without_system_roots_loads_verified_public_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    assert context.cert_store_stats()["x509_ca"] == 0
    monkeypatch.setattr("godfather_worker.client.ssl.create_default_context", lambda: context)
    client = WorkerClient("https://example.invalid", "")
    assert any(
        isinstance(handler, HTTPSHandler)
        for handler in client.opener.handlers  # type: ignore[attr-defined]
    )
    assert context.cert_store_stats()["x509_ca"] > 0
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


@pytest.mark.parametrize(
    "reason,expected",
    [
        (ssl.SSLCertVerificationError("private diagnostic"), "certificate verification failed"),
        (socket.gaierror("private diagnostic"), "could not be resolved"),
        (TimeoutError("private diagnostic"), "did not respond"),
    ],
)
def test_connection_errors_are_actionable_without_leaking_details(
    reason: Exception,
    expected: str,
) -> None:
    message = connection_error(URLError(reason))
    assert expected in message and "private diagnostic" not in message


def test_frozen_connection_probe_requires_unapproved_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = Mock(side_effect=HTTPError("", 404, "pending", Message(), None))
    monkeypatch.setattr(Pairing, "exchange", exchange)
    check_connection("https://example.invalid")
    assert exchange.call_count == 1
    exchange.side_effect = URLError(ssl.SSLCertVerificationError("untrusted"))
    with pytest.raises(URLError):
        check_connection("https://example.invalid")


def test_failed_pairing_preserves_code_and_never_claims_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip(
        "tkinter",
        reason="GUI adapter check requires Tk; core worker does not",
        exc_type=ImportError,
    )
    from godfather_worker.desktop_app import Application

    app = Application.__new__(Application)
    app.root = Mock()
    app.address = Mock()
    app.address.get.return_value = "https://example.invalid"
    app.identity, app.tray = None, None
    app.pairing_busy, app.destroyed = False, False
    app.status, app.code, app.connection_state = Mock(), Mock(), Mock()
    app.secure_label = Mock()
    app.connection_badge, app.connect_button, app.address_entry, app.notebook = (
        Mock(),
        Mock(),
        Mock(),
        Mock(),
    )
    app.store = Mock()
    import queue

    app.events = queue.Queue()
    # Deterministic event production; no network or background timing dependency.
    monkeypatch.setattr(app, "background", lambda action: action())
    monkeypatch.setattr(
        "godfather_worker.desktop_app.await_approval",
        Mock(side_effect=URLError(ssl.SSLCertVerificationError("untrusted"))),
    )
    browser = Mock()
    monkeypatch.setattr("godfather_worker.desktop_app.webbrowser.open", browser)
    app.connect()
    challenge = urlsplit(browser.call_args.args[0]).fragment.split("=", 1)[1][:12].upper()
    assert challenge in app.code.set.call_args.args[0]
    app.root.update_idletasks.assert_called_once()
    app.pump()
    assert "inactive" in app.code.set.call_args.args[0]
    assert challenge in app.code.set.call_args.args[0]
    assert "certificate verification failed" in app.status.set.call_args.args[0]
    assert app.connection_state.set.call_args.args == ("DISCONNECTED",)
    assert not app.pairing_busy and app.identity is None
    app.store.write.assert_not_called()


def test_store_refuses_silent_identity_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = Mock()
    backend.get_password.return_value = "existing"
    monkeypatch.setattr("godfather_worker.native_desktop.platform.system", lambda: "Windows")
    monkeypatch.setattr("godfather_worker.native_desktop.store", lambda: backend)
    with pytest.raises(OSError, match="already exists"):
        CredentialStore().write("replacement")
    backend.set_password.assert_not_called()


def test_startup_setting_reflects_registered_executable_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    registry = MagicMock()
    registry.QueryValueEx.return_value = (f'"{sys.executable}" --login', 1)
    monkeypatch.setattr("godfather_worker.native_desktop.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "godfather_worker.native_desktop.importlib.import_module", lambda _: registry
    )
    assert login_startup_enabled()
    registry.QueryValueEx.return_value = ('"another-app.exe" --login', 1)
    assert not login_startup_enabled()
    registry.SetValueEx.assert_not_called()
