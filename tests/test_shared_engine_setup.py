"""Managed engine scope, runtime validation and actual loopback mutual TLS."""

import json
import socket
import ssl
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from godfather_contracts import Contract
from godfather_contracts.shared_engine import (
    EngineDevice,
    EngineGroup,
    EngineMember,
    EngineProposal,
    LocalEngineConsent,
    private_address,
)
from godfather_worker import llama_runtime
from godfather_worker.desktop import Contribution, Controller, LimitedClient
from godfather_worker.shared_engine import Engine, remote_devices
from godfather_worker.shared_engine_transport import Bridge, contexts, hostname, identity


def group_fixture(folder: Path) -> tuple[LocalEngineConsent, EngineGroup]:
    leader, peer = uuid4(), uuid4()
    proposal = EngineProposal(
        id=uuid4(),
        leader_node_id=leader,
        node_ids=[leader, peer],
        workspace_id=uuid4(),
        name="Test group",
        model_name="fixture.gguf",
        mode="local_network",
    )
    model = folder / "fixture.gguf"
    model.write_bytes(b"GGUFfixture-not-real-weights")
    devices = [EngineDevice(id="CPU", name="CPU", backend="cpu")]
    consent = LocalEngineConsent(
        proposal=proposal,
        node_id=leader,
        credential_id=uuid4(),
        devices=devices,
        backend="cpu",
        host="127.0.0.1",
        port=50053,
        model_path=str(model),
    )
    _, _, pem = identity(folder, leader, proposal.id)
    members = [
        EngineMember(
            node_id=leader,
            name="Leader",
            owner="First",
            approved=True,
            devices=devices,
            host=consent.host,
            port=consent.port,
            certificate=pem,
            phase="ready",
        ),
        EngineMember(
            node_id=peer,
            name="Peer",
            owner="Second",
            approved=True,
            devices=devices,
            host="10.0.0.2",
            port=50053,
            phase="ready",
        ),
    ]
    from godfather_contracts import SharedInferenceGroup

    topology = SharedInferenceGroup(
        id=proposal.id,
        name=proposal.name,
        mode=proposal.mode,
        leader_node_id=leader,
        node_ids=proposal.node_ids,
        model=proposal.model_alias,
        engine="llama_cpp",
        parallelism="pipeline",
        device_count=2,
        private_transport=True,
    )
    return consent, EngineGroup(
        proposal=proposal, members=members, desired_running=True, generation=1, group=topology
    )


@pytest.mark.parametrize(
    "address",
    ["192.168.1.10", "10.0.0.1", "172.20.0.1", "100.64.0.3", "fd00::1", "127.0.0.1", "::1"],
)
def test_private_routes(address: str) -> None:
    assert private_address(address) == address


@pytest.mark.parametrize(
    "address", ["0.0.0.0", "::", "8.8.8.8", "example.com", "169.254.1.2", "224.0.0.1"]
)
def test_no_wildcard_public_or_dns_rpc_target(address: str) -> None:
    with pytest.raises(ValueError):
        private_address(address)


def test_runtime_download_requires_explicit_local_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opener = Mock()
    monkeypatch.setattr(llama_runtime, "build_opener", opener)
    with pytest.raises(ValueError, match="Allow the verified"):
        llama_runtime.install(tmp_path, "cpu", False)
    opener.assert_not_called()


def test_device_inventory_ignores_logs_and_reports_actual_backends(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = llama_runtime.Runtime(tmp_path, tmp_path / "server", tmp_path / "rpc")
    monkeypatch.setattr(
        llama_runtime,
        "run_probe",
        lambda *_: (
            "load_backend: Vulkan is enabled\nAvailable devices:\n"
            "  Vulkan0: Example GPU (8192 MiB, 7000 MiB free)\n"
            "  Metal1: Apple GPU (16384 MiB, 9000 MiB free)\n"
            "ggml_vulkan: A backend log after the inventory is not a device\n"
        ),
    )
    values = llama_runtime.devices(runtime)
    assert [d.id for d in values] == ["Vulkan0", "Metal1", "CPU"]
    assert values[0].memory_bytes == 8192 * 1024**2
    assert values[0].name == "Example GPU"
    assert values[1].backend == "metal"
    monkeypatch.setattr(llama_runtime, "run_probe", lambda *_: "Unexpected version")
    with pytest.raises(ValueError, match="device inventory"):
        llama_runtime.devices(runtime)


def test_runtime_integrity_is_checked_before_reuse(tmp_path: Path) -> None:
    root = llama_runtime.runtime_folder(tmp_path, "cpu", "windows-x64")
    root.mkdir(parents=True)
    (root / "llama-server.exe").write_bytes(b"changed")
    (root / "ggml-rpc-server.exe").write_bytes(b"changed")
    (root / "verified.json").write_text(
        json.dumps(
            {
                "archive_sha256": llama_runtime.catalog()["artifacts"]["windows-x64/cpu"][1],
                "files": {"llama-server.exe": "0" * 64},
            }
        )
    )
    with pytest.raises(ValueError, match="failed verification"):
        llama_runtime.existing(tmp_path, "cpu", "windows-x64")


def test_engine_environment_does_not_inherit_keys_or_override_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (
        "OPENAI_API_KEY",
        "HF_TOKEN",
        "LLAMA_ARG_HOST",
        "LLAMA_ARG_MODEL_URL",
        "LLAMA_ARG_AGENT",
        "PYTHONPATH",
    ):
        monkeypatch.setenv(key, "should-not-inherit")
    env = llama_runtime.environment(tmp_path)
    assert "should-not-inherit" not in env.values()
    assert env["HF_HUB_OFFLINE"] == "1"


def test_local_approval_is_bound_to_proposal_devices_certificate_and_credential(
    tmp_path: Path,
) -> None:
    pytest.importorskip("tkinter", exc_type=ImportError)
    from godfather_worker.shared_inference_ui import load_consent, save_consent

    consent, group = group_fixture(tmp_path)
    save_consent(tmp_path, consent)
    assert load_consent(tmp_path, group, str(consent.credential_id)) == consent
    assert load_consent(tmp_path, group, str(uuid4())) is None
    group.members[0].devices = [EngineDevice(id="Vulkan0", name="Other GPU", backend="vulkan")]
    assert load_consent(tmp_path, group, str(consent.credential_id)) is None


def test_managed_controller_preserves_normal_settings_and_passes_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consent, group = group_fixture(tmp_path)
    engine: Any = Mock(alive=True, group=group)
    from godfather_model_gateway import ProviderConfig

    engine.provider = ProviderConfig(
        id="shared-test",
        provider="openai_compatible",
        url="http://127.0.0.1:9000/v1",
        shared_inference_group_id=group.proposal.id,
    )
    captured: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> None:
        captured.update(args=args, **kwargs)

    monkeypatch.setattr("godfather_worker.cli.main", run)
    controller = Controller(
        {"owner_id": str(uuid4()), "token": "fixture", "origin": "http://127.0.0.1:8000"},
        tmp_path,
        Mock(),
    )
    settings = Contribution(inference=True, account_providers=True)
    (tmp_path / "shared-engine").mkdir(exist_ok=True)
    controller.start(settings, engine)
    assert controller.thread
    controller.thread.join(3)
    assert Contribution.model_validate_json((tmp_path / "settings.json").read_text()) == settings
    args = captured["args"]
    assert "--shared-engine-setup" in args and "--managed-shared-inference" in args
    assert "--account-providers" not in args and "--allow-model-installation" not in args
    providers = json.loads(Path(args[args.index("--inference-config") + 1]).read_text())
    assert len(providers) == 1 and providers[0]["shared_inference_group_id"] == str(
        group.proposal.id
    )


@dataclass
class Echo:
    listener: socket.socket
    done: threading.Event
    thread: threading.Thread


@pytest.fixture
def echo() -> Any:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    listener.settimeout(0.2)
    stop = threading.Event()

    def run() -> None:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with conn:
                conn.settimeout(3)
                try:
                    while data := conn.recv(65536):
                        conn.sendall(data)
                except OSError:
                    pass

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    yield Echo(listener, stop, thread)
    stop.set()
    listener.close()
    thread.join(3)


def test_real_bidirectional_mtls_bridge_and_unapproved_peer_denied(
    tmp_path: Path, echo: Echo
) -> None:
    group_id, first, second, rogue = uuid4(), uuid4(), uuid4(), uuid4()
    folder_a, folder_b, folder_rogue = tmp_path / "a", tmp_path / "b", tmp_path / "rogue"
    _, _, pem_a = identity(folder_a, first, group_id)
    _, _, pem_b = identity(folder_b, second, group_id)
    server = Bridge(
        "127.0.0.1",
        0,
        echo.listener.getsockname(),
        contexts(folder_b, second, group_id, pem_a, True),
        pem_a,
        server=True,
    )
    proxy = Bridge(
        "127.0.0.1",
        0,
        ("127.0.0.1", server.port),
        contexts(folder_a, first, group_id, pem_b, False),
        pem_b,
        server=False,
        peer_name=hostname(second, group_id),
    )
    try:
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=3) as client:
            for payload in (b"approved engine RPC", bytes(range(256)) * 1000, b"next RPC"):
                client.sendall(payload)
                received = bytearray()
                while len(received) < len(payload):
                    chunk = client.recv(min(65536, len(payload) - len(received)))
                    assert chunk
                    received.extend(chunk)
                assert received == payload
        unapproved = contexts(folder_rogue, rogue, group_id, pem_b, False)
        with (
            pytest.raises((OSError, ssl.SSLError)),
            unapproved.wrap_socket(
                socket.create_connection(("127.0.0.1", server.port), timeout=3),
                server_hostname=hostname(second, group_id),
            ) as client,
        ):
            client.sendall(b"no consent")
            assert client.recv(100) != b"no consent"
    finally:
        proxy.close()
        server.close()
    assert not proxy.thread.is_alive() and not server.thread.is_alive()


def test_engine_rejects_changed_local_devices_before_spawning(tmp_path: Path) -> None:
    consent, group = group_fixture(tmp_path)
    group.members[0].approved = False
    runtime = llama_runtime.Runtime(tmp_path, tmp_path / "server", tmp_path / "rpc")
    engine = Engine(tmp_path, consent, runtime, group)
    with pytest.raises(ValueError, match="local device approval"):
        engine.start()
    assert not engine.processes and not engine.bridges


def test_pinned_native_rpc_names_require_every_approved_peer() -> None:
    output = "Available devices:\n  RPC0: 127.0.0.1:5001 (10 MiB, 9 MiB free)\n"
    assert remote_devices(output, ["127.0.0.1:5001"]) == ["RPC0"]
    with pytest.raises(ValueError, match="could not be reached securely"):
        remote_devices(output, ["127.0.0.1:5001", "127.0.0.1:5002"])


def test_cancelled_engine_cannot_spawn_another_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consent, group = group_fixture(tmp_path)
    runtime = llama_runtime.Runtime(tmp_path, tmp_path / "server", tmp_path / "rpc")
    engine = Engine(tmp_path, consent, runtime, group)
    spawn = Mock()
    monkeypatch.setattr("godfather_worker.shared_engine.subprocess.Popen", spawn)
    engine.stop()
    with pytest.raises(ValueError, match="cancelled"):
        engine.spawn(runtime.server, [])
    spawn.assert_not_called()


def test_peer_launch_exposes_only_selected_devices_on_raw_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consent, group = group_fixture(tmp_path)
    local = consent.model_copy(
        update={"node_id": group.proposal.node_ids[1], "model_path": None, "host": "10.0.0.2"}
    )
    runtime = llama_runtime.Runtime(tmp_path, tmp_path / "server", tmp_path / "rpc")
    engine = Engine(tmp_path, local, runtime, group)
    spawn = Mock()
    engine.spawn = spawn  # type: ignore[method-assign]
    engine.wait_port = Mock()  # type: ignore[method-assign]
    monkeypatch.setattr("godfather_worker.shared_engine.contexts", Mock())
    bridge = Mock()
    monkeypatch.setattr("godfather_worker.shared_engine.Bridge", bridge)
    engine.start_peer()
    args = spawn.call_args.args[1]
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert args[args.index("--device") + 1] == "CPU"
    assert bridge.call_args.args[0] == "10.0.0.2" and bridge.call_args.kwargs["server"]


def test_leader_launch_is_offline_loopback_and_uses_confirmed_rpc_devices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    consent, group = group_fixture(tmp_path)
    _, _, pem = identity(tmp_path / "peer", group.members[1].node_id, group.proposal.id)
    group.members[1].certificate = pem
    runtime = llama_runtime.Runtime(tmp_path, tmp_path / "server", tmp_path / "rpc")
    engine = Engine(tmp_path, consent, runtime, group)
    args: list[str] = []

    def spawn(executable: Path, arguments: list[str]) -> None:
        args.extend(arguments)
        engine.processes.append(Mock(poll=Mock(return_value=None)))

    engine.spawn = spawn  # type: ignore[method-assign]
    monkeypatch.setattr("godfather_worker.shared_engine.contexts", Mock())
    monkeypatch.setattr("godfather_worker.shared_engine.Bridge", Mock(return_value=Mock(port=6001)))
    monkeypatch.setattr(
        "godfather_worker.shared_engine.run_probe",
        lambda *_: "Available devices:\n RPC0: 127.0.0.1:6001 (10 MiB, 9 MiB free)\n",
    )
    client = Mock(url="http://127.0.0.1:6000")

    def response(request: Any, **_: Any) -> io.BytesIO:
        value = (
            {"status": "ok"}
            if request.full_url.endswith("/health")
            else {"data": [{"id": group.proposal.model_alias}]}
        )
        return io.BytesIO(json.dumps(value).encode())

    client.opener.open.side_effect = response
    monkeypatch.setattr("godfather_worker.shared_engine.WorkerClient", lambda *_: client)
    engine.start_leader()
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert args[args.index("--device") + 1] == "RPC0"
    assert {"--offline", "--no-agent", "--no-webui", "--no-mmproj"} <= set(args)
    assert engine.provider and engine.provider.shared_inference_group_id == group.proposal.id
    assert client.opener.open.call_args_list[0].args[0].full_url.endswith("/health")


def panel_fixture(tmp_path: Path) -> tuple[Any, LocalEngineConsent, EngineGroup]:
    pytest.importorskip("tkinter", exc_type=ImportError)
    from godfather_worker.shared_inference_ui import SharedInference, save_consent

    panel: Any = object.__new__(SharedInference)
    consent, group = group_fixture(tmp_path)
    save_consent(tmp_path, consent)
    panel.app = Mock(
        folder=tmp_path, identity={"credential_id": str(consent.credential_id)}, closing=False
    )
    panel.app.controller.running = True
    panel.groups = {}
    panel.table = Mock()
    panel.table.selection.return_value = []
    panel.table.get_children.return_value = []
    panel.message = Mock()
    panel.selection = Mock()
    panel.engine = None
    panel.ready = panel.activating = panel.stopping = panel.suspended = False
    panel.busy = panel.polling = False
    panel.revision = 0
    panel.revoked = set()
    panel.stop_notice = ""
    panel.progress = Mock()
    panel.cancel = threading.Event()
    panel.node_id = consent.node_id
    panel.endpoint_group_id = None
    panel.local_models = {group.proposal.id: consent.model_path}
    panel.failed_run = panel.pending = None
    panel.activate = Mock()
    panel.stop_local = Mock()
    return panel, consent, group


def action_panel(tmp_path: Path) -> tuple[Any, LocalEngineConsent, EngineGroup, list[Any]]:
    panel, consent, group = panel_fixture(tmp_path)
    group.desired_running = False
    panel.groups = {str(group.proposal.id): group}
    panel.table.selection.return_value = [str(group.proposal.id)]
    panel.app.settings.cpu_cores = 2
    panel.available = consent.devices
    panel.device_list = Mock(curselection=Mock(return_value=(0,)))
    panel.backend = Mock(get=Mock(return_value="cpu"))
    panel.detected_backend = "cpu"
    panel.host = Mock(get=Mock(return_value=consent.host))
    panel.port = Mock(get=Mock(return_value=str(consent.port)))
    panel.client = Mock(return_value=Mock())
    work: list[Any] = []
    panel.app.background.side_effect = work.append
    panel.deliver = lambda apply: apply()
    return panel, consent, group, work


def test_approval_acknowledges_pending_then_committed_result_without_waiting_for_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, _, group, work = action_panel(tmp_path)
    monkeypatch.setattr(
        "godfather_worker.shared_inference_ui.messagebox.askyesno", lambda *a, **k: True
    )
    panel.client().post_document.return_value = group.model_dump(mode="json")
    panel.approve()
    assert panel.busy
    assert "Saving" in panel.message.set.call_args.args[0]
    panel.progress.start.assert_called_once()
    work.pop()()
    assert not panel.busy
    assert "This computer is approved" in panel.message.set.call_args.args[0]
    assert panel.groups[str(group.proposal.id)].members[0].approved


def test_selected_lan_endpoint_is_saved_and_sent_in_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, _, group, work = action_panel(tmp_path)
    from godfather_worker.shared_inference_ui import consent_path

    panel.host.get.return_value = "10.0.0.129"
    panel.port.get.return_value = "50100"
    confirm = Mock(return_value=True)
    monkeypatch.setattr("godfather_worker.shared_inference_ui.messagebox.askyesno", confirm)
    panel.client().post_document.return_value = group.model_dump(mode="json")
    panel.approve()
    assert "10.0.0.129, port 50100" in confirm.call_args.args[1]
    work.pop()()
    payload = panel.client().post_document.call_args.args[1]
    saved = LocalEngineConsent.model_validate_json(
        consent_path(tmp_path, group.proposal.id).read_text()
    )
    assert (payload.host, payload.port) == (saved.host, saved.port) == ("10.0.0.129", 50100)


@pytest.mark.parametrize(
    "host,port", [("10.0.0.129", "50053"), ("127.0.0.1", "50100"), ("bad", "x")]
)
def test_changed_endpoint_requires_new_local_approval_before_start(
    tmp_path: Path, host: str, port: str
) -> None:
    panel, _, _, work = action_panel(tmp_path)
    panel.host.get.return_value, panel.port.get.return_value = host, port
    panel.control("start")
    assert "Approve this computer to save" in panel.message.set.call_args.args[0]
    assert not work
    panel.client().post_document.assert_not_called()


def test_lan_addresses_precede_tailscale_without_discarding_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("tkinter", exc_type=ImportError)
    from godfather_worker.shared_inference_ui import local_addresses

    monkeypatch.setattr(
        "godfather_worker.shared_inference_ui.psutil.net_if_addrs",
        lambda: {
            "example": [
                Mock(address=a) for a in ("100.69.1.2", "10.0.0.129", "127.0.0.1", "8.8.8.8")
            ]
        },
    )
    assert local_addresses() == ["10.0.0.129", "100.69.1.2"]


@pytest.mark.parametrize("preserve_error", [False, True])
def test_last_owner_approval_refreshes_waiting_feedback_without_erasing_errors(
    tmp_path: Path, preserve_error: bool
) -> None:
    panel, consent, ready, _ = action_panel(tmp_path)
    from godfather_worker.shared_inference_ui import approval_message

    waiting = ready.model_copy(deep=True)
    waiting.group = None
    waiting.members[1].approved = False
    panel.groups = {str(waiting.proposal.id): waiting}
    panel.message.get.return_value = (
        "Connection unavailable" if preserve_error else approval_message(waiting)
    )
    panel.received(consent.node_id, [ready])
    if preserve_error:
        panel.message.set.assert_not_called()
    else:
        assert "All owners have approved" in panel.message.set.call_args.args[0]


def test_missing_devices_and_cancelled_approval_explain_why_nothing_was_granted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, _, _, work = action_panel(tmp_path)
    panel.device_list.curselection.return_value = ()
    panel.approve()
    assert "Detect and select devices" in panel.message.set.call_args.args[0]
    panel.device_list.curselection.return_value = (0,)
    monkeypatch.setattr(
        "godfather_worker.shared_inference_ui.messagebox.askyesno", lambda *a, **k: False
    )
    panel.approve()
    assert "Approval cancelled" in panel.message.set.call_args.args[0]
    assert not work
    panel.client().post_document.assert_not_called()


def test_withdrawal_shows_pending_then_withdrawn_row_and_blocks_local_restart(
    tmp_path: Path,
) -> None:
    panel, consent, group, work = action_panel(tmp_path)
    from godfather_worker.shared_inference_ui import consent_path

    panel.pending = group
    result = group.model_copy(deep=True)
    result.group = None
    result.members[0].approved = False
    result.members[0].phase = "stopped"
    panel.client().post_document.return_value = result.model_dump(mode="json")
    panel.withdraw()
    assert panel.busy and panel.pending is None
    assert "withdrawing" in panel.message.set.call_args.args[0]
    work.pop()()
    assert not consent_path(tmp_path, group.proposal.id).exists()
    assert group.proposal.id in panel.revoked
    assert "Approval withdrawn" in panel.message.set.call_args.args[0]
    assert panel.table.insert.call_args.kwargs["values"][1] == "Withdrawn"
    group.desired_running = True
    panel.received(consent.node_id, [group])
    panel.activate.assert_not_called()


def test_network_failure_is_visible_and_does_not_claim_withdrawal_succeeded(tmp_path: Path) -> None:
    panel, _, _, work = action_panel(tmp_path)
    panel.client().post_document.side_effect = OSError("Connection unavailable")
    panel.withdraw()
    work.pop()()
    assert not panel.busy
    assert "withdrawal was not confirmed" in panel.message.set.call_args.args[0]
    panel.progress.stop.assert_called()


@pytest.mark.parametrize("confirmed", [True, False])
def test_delete_requires_confirmation_and_removes_row_only_after_server_acknowledgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, confirmed: bool
) -> None:
    panel, _, group, work = action_panel(tmp_path)
    monkeypatch.setattr(
        "godfather_worker.shared_inference_ui.messagebox.askyesno", lambda *a, **k: confirmed
    )
    panel.client().post_document.return_value = {"removed": True, "scope": "setup"}
    panel.delete()
    assert str(group.proposal.id) in panel.groups
    if not confirmed:
        assert "Deletion cancelled" in panel.message.set.call_args.args[0]
        assert not work
        return
    assert "Deleting" in panel.message.set.call_args.args[0]
    work.pop()()
    assert str(group.proposal.id) not in panel.groups
    assert "Setup deleted" in panel.message.set.call_args.args[0]


def test_failed_delete_keeps_row_and_shows_retry_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel, _, group, work = action_panel(tmp_path)
    monkeypatch.setattr(
        "godfather_worker.shared_inference_ui.messagebox.askyesno", lambda *a, **k: True
    )
    panel.client().post_document.side_effect = OSError("Connection unavailable")
    panel.delete()
    work.pop()()
    assert str(group.proposal.id) in panel.groups
    assert "deletion was not confirmed" in panel.message.set.call_args.args[0]


def test_old_poll_cannot_restore_a_deleted_or_unapproved_row_after_mutation(tmp_path: Path) -> None:
    panel, consent, group, work = action_panel(tmp_path)
    panel.client().post_document.return_value = {
        "node_id": str(consent.node_id),
        "groups": [group.model_dump(mode="json")],
    }
    queued: list[Any] = []
    panel.deliver = queued.append
    panel.refresh()
    work.pop()()
    assert len(queued) == 1
    panel.revision += 1  # A mutation started after this poll's snapshot.
    panel.groups.clear()
    queued.pop()()
    assert not panel.groups
    panel.table.insert.assert_not_called()


def test_setup_selection_shows_saved_endpoint_and_refresh_preserves_unsaved_edits(
    tmp_path: Path,
) -> None:
    panel, consent, _, _ = action_panel(tmp_path)
    from godfather_worker.shared_inference_ui import SharedInference

    for name in (
        "approve_button",
        "start_button",
        "withdraw_button",
        "delete_button",
        "setup_button",
        "refresh_button",
        "detect_button",
        "menu",
        "detail",
    ):
        setattr(panel, name, Mock())
    SharedInference.selection(panel)
    panel.host.set.assert_called_once_with(consent.host)
    panel.port.set.assert_called_once_with(str(consent.port))
    assert "saved address: 10.0.0.2" in panel.detail.set.call_args.args[0]
    panel.host.set.reset_mock()
    panel.port.set.reset_mock()
    SharedInference.selection(panel)
    panel.host.set.assert_not_called()
    panel.port.set.assert_not_called()


def test_refresh_from_a_previous_connection_cannot_enter_current_account(tmp_path: Path) -> None:
    panel, consent, group, work = action_panel(tmp_path)
    panel.client().post_document.return_value = {
        "node_id": str(consent.node_id),
        "groups": [group.model_dump(mode="json")],
    }
    queued: list[Any] = []
    panel.deliver = queued.append
    panel.refresh()
    work.pop()()
    panel.app.identity = {"credential_id": str(uuid4())}
    panel.groups.clear()
    queued.pop()()
    assert not panel.groups
    panel.table.insert.assert_not_called()


def test_explicit_refresh_and_busy_click_always_show_feedback(tmp_path: Path) -> None:
    panel, consent, _, work = action_panel(tmp_path)
    panel.client().post_document.return_value = {"node_id": str(consent.node_id), "groups": []}
    panel.refresh(manual=True)
    assert "Refreshing" in panel.message.set.call_args.args[0]
    work.pop()()
    assert "Refresh complete" in panel.message.set.call_args.args[0]
    panel.busy = True
    panel.task(Mock(), Mock(), pending="Should not replace current request")
    assert "already in progress" in panel.message.set.call_args.args[0]
    assert not work


def test_context_menu_selects_clicked_row_and_blank_space_does_not_target_another_setup(
    tmp_path: Path,
) -> None:
    panel, _, group, _ = action_panel(tmp_path)
    panel.menu = Mock()
    panel.table.identify_row.return_value = str(group.proposal.id)
    event = Mock(y=40, x_root=100, y_root=200)
    panel.context_menu(event)
    panel.table.selection_set.assert_called_with(str(group.proposal.id))
    panel.menu.tk_popup.assert_called_once_with(100, 200)
    panel.menu.reset_mock()
    panel.table.identify_row.return_value = ""
    panel.context_menu(event)
    panel.menu.tk_popup.assert_not_called()


def test_wizard_finishes_current_work_before_starting_and_waits_for_peers(tmp_path: Path) -> None:
    panel, consent, group = panel_fixture(tmp_path)
    group.members[1].phase = "starting"
    panel.received(consent.node_id, [group])
    panel.app.controller.maintenance_event.set.assert_not_called()
    panel.activate.assert_not_called()
    group.members[1].phase = "ready"
    panel.received(consent.node_id, [group])
    panel.app.controller.maintenance_event.set.assert_called_once()
    panel.activate.assert_not_called()
    assert panel.worker_stopped()
    panel.activate.assert_called_once_with(group, consent)


def test_pending_start_is_removed_when_an_owner_withdraws(tmp_path: Path) -> None:
    panel, consent, group = panel_fixture(tmp_path)
    panel.received(consent.node_id, [group])
    assert panel.pending
    group.desired_running = False
    panel.received(consent.node_id, [group])
    assert not panel.worker_stopped()
    panel.activate.assert_not_called()


def test_withdrawal_or_lost_workspace_stops_a_running_engine(tmp_path: Path) -> None:
    panel, consent, group = panel_fixture(tmp_path)
    panel.engine = Mock(group=group, alive=True)
    panel.ready = True
    panel.received(consent.node_id, [])
    panel.stop_local.assert_called_once()


def test_paused_owner_never_auto_starts_an_approved_group(tmp_path: Path) -> None:
    panel, consent, group = panel_fixture(tmp_path)
    panel.suspended = True
    panel.app.controller.running = False
    panel.received(consent.node_id, [group])
    panel.activate.assert_not_called()


def test_ordinary_desktop_still_strips_gpus_but_approved_engine_reports_selected_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from godfather_contracts import Registration
    from godfather_worker.client import WorkerClient
    from godfather_worker.simulated import profile

    captured: list[Contract] = []
    monkeypatch.setattr(
        WorkerClient, "post_document", lambda self, path, payload: captured.append(payload)
    )
    registration = Registration(**profile("LV-01").model_dump(), session_id=uuid4())
    normal = LimitedClient("fixture", Contribution(), "http://127.0.0.1:8000")
    normal.post_document("/fixture", registration)
    assert isinstance(captured[-1], Registration) and not captured[-1].resources.gpus
    engine = Mock(alive=True, gpu_advertisement=Mock(return_value=registration.resources.gpus))
    managed = LimitedClient("fixture", Contribution(), "http://127.0.0.1:8000", engine)
    managed.post_document("/fixture", registration)
    assert (
        isinstance(captured[-1], Registration)
        and captured[-1].resources.gpus == registration.resources.gpus
    )
