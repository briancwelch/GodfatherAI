"""Origin binding and approval polling regression checks without real credentials."""

import json
import threading
from email.message import Message
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
from godfather_worker.desktop import Pairing, coordinator_origin
from godfather_worker.native_desktop import CredentialStore
from godfather_worker.pairing import await_approval


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


def test_store_refuses_silent_identity_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = Mock()
    backend.get_password.return_value = "existing"
    monkeypatch.setattr("godfather_worker.native_desktop.platform.system", lambda: "Windows")
    monkeypatch.setattr("godfather_worker.native_desktop.store", lambda: backend)
    with pytest.raises(OSError, match="already exists"):
        CredentialStore().write("replacement")
    backend.set_password.assert_not_called()
