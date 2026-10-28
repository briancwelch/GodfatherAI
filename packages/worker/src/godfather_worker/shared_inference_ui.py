"""Owner-local shared inference wizard and managed engine lifecycle."""

import ipaddress
import threading
import tkinter as tk
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from time import monotonic
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError
from uuid import UUID

import psutil
from godfather_contracts import Contract
from godfather_contracts.shared_engine import (
    EngineAction,
    EngineApproval,
    EngineCreate,
    EngineDelete,
    EngineDevice,
    EngineGroup,
    EngineReport,
    LocalEngineConsent,
    private_address,
)

from godfather_worker.client import WorkerClient
from godfather_worker.desktop import API_ORIGIN
from godfather_worker.llama_runtime import devices, existing, gguf, install, variants
from godfather_worker.shared_engine import Engine
from godfather_worker.shared_engine_transport import identity

if TYPE_CHECKING:
    from godfather_worker.desktop_app import Application

PREFIX = "/api/v1/workers/shared-engine/"
MODES = {
    "GPUs in this computer": "single_host",
    "Computers on a local network": "local_network",
    "Computers across locations": "wide_area",
}


class Options(Contract):
    workspace_id: UUID | None = None


def local_addresses() -> list[str]:
    addresses = []
    for entries in psutil.net_if_addrs().values():
        for entry in entries:
            try:
                value = private_address(str(entry.address))
                if not ipaddress.ip_address(value).is_loopback:
                    addresses.append(value)
            except ValueError:
                pass
    return sorted(
        set(addresses),
        key=lambda value: (
            ipaddress.ip_address(value) in ipaddress.ip_network("100.64.0.0/10"),
            value,
        ),
    )


def approval_message(group: EngineGroup) -> str:
    return (
        f'This computer is approved for "{group.proposal.name}" '
        f"({str(group.proposal.id)[:8]}). "
        + (
            "All owners have approved; select Configure and Start on the initiating computer."
            if group.group
            else "Waiting for the other computer owners to approve."
        )
    )


def consent_path(folder: Path, group_id: UUID) -> Path:
    return folder / "shared-engine/consents" / (group_id.hex + ".json")


def save_consent(folder: Path, consent: LocalEngineConsent) -> None:
    path = consent_path(folder, consent.proposal.id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(consent.model_dump_json(), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def load_consent(folder: Path, group: EngineGroup, credential: str) -> LocalEngineConsent | None:
    try:
        local = LocalEngineConsent.model_validate_json(
            consent_path(folder, group.proposal.id).read_text(encoding="utf-8")
        )
        own = next(m for m in group.members if m.node_id == local.node_id)
        _, _, pem = identity(folder, local.node_id, group.proposal.id)
        if (
            local.proposal == group.proposal
            and str(local.credential_id) == credential
            and own.approved
            and own.devices == local.devices
            and own.certificate == pem
            and own.host == local.host
            and own.port == local.port
        ):
            return local
    except (OSError, ValueError, StopIteration):
        pass
    return None


class SharedInference:
    def __init__(self, app: "Application", parent: ttk.Frame) -> None:
        self.app = app
        self.groups: dict[str, EngineGroup] = {}
        self.node_id: UUID | None = None
        self.engine: Engine | None = None
        self.ready = False
        self.activating = False
        self.stopping = False
        self.polling = False
        self.last_seen = monotonic()
        self.failed_run: tuple[UUID, int] | None = None
        self.pending: EngineGroup | None = None
        self.local_models: dict[UUID, str] = {}
        self.available: list[EngineDevice] = []
        self.detected_backend = ""
        self.cancel = threading.Event()
        self.busy = False
        self.revision = 0
        self.revoked: set[UUID] = set()
        self.stop_notice = ""
        self.wizard_window: tk.Toplevel | None = None
        self.suspended = False
        self.message = tk.StringVar(
            value="Connect this computer, then set up a shared local model."
        )
        backends = variants()
        preferred = "metal" if "metal" in backends else "vulkan" if "vulkan" in backends else "cpu"
        self.backend = tk.StringVar(value=preferred)
        self.allow_download = tk.BooleanVar(value=False)
        self.host = tk.StringVar(value=next(iter(local_addresses()), "127.0.0.1"))
        self.port = tk.StringVar(value="50053")
        self.endpoint_group_id: UUID | None = None
        controls = ttk.Frame(parent, padding=(16, 10))
        controls.pack(fill="x")
        self.setup_button = ttk.Button(
            controls, text="Set up Shared Inference", command=self.wizard
        )
        self.setup_button.pack(side="left")
        self.refresh_button = ttk.Button(
            controls, text="Refresh", command=lambda: self.refresh(manual=True)
        )
        self.refresh_button.pack(side="left", padx=6)
        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.pack(side="bottom", fill="x", padx=16, pady=(0, 8))
        panes = ttk.Panedwindow(parent, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=16, pady=8)
        left, approval = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(approval, weight=2)
        action_area = ttk.Frame(approval)
        action_area.pack(side="bottom", fill="x")
        viewport = ttk.Frame(approval)
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, highlightthickness=0, width=420, height=180)
        scroll = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        right = ttk.Frame(canvas)
        item = canvas.create_window(0, 0, window=right, anchor="nw")

        def content_changed(_: object = None) -> None:
            for child in right.winfo_children():
                if isinstance(child, ttk.Label):
                    child.configure(wraplength=max(100, right.winfo_width() - 12))
            canvas.configure(scrollregion=canvas.bbox("all"))

        right.bind("<Configure>", content_changed)
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        self.table = ttk.Treeview(left, columns=("group", "state"), show="headings", height=5)
        self.table.heading("group", text="Shared model")
        self.table.heading("state", text="Status")
        self.table.column("group", width=130, minwidth=70)
        self.table.column("state", width=95, minwidth=60)
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.selection)
        self.menu = tk.Menu(self.table, tearoff=False)
        self.menu.add_command(label="Delete setup...", command=self.delete)
        for binding in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.table.bind(binding, self.context_menu)
        for binding in ("<Menu>", "<Shift-F10>"):
            self.table.bind(binding, self.keyboard_menu)
        self.table.bind("<Delete>", lambda _: self.delete())
        self.delete_button = ttk.Button(left, text="Delete setup...", command=self.delete)
        self.delete_button.pack(anchor="w", pady=(6, 0))
        self.detail = tk.StringVar(value="Choose a group to review participation.")
        ttk.Label(right, textvariable=self.detail, wraplength=550).pack(fill="x", pady=(0, 8))
        row = ttk.Frame(right)
        row.pack(fill="x")
        ttk.Label(row, text="Local engine backend").pack(side="left")
        ttk.Combobox(
            row, textvariable=self.backend, values=variants(), state="readonly", width=10
        ).pack(side="left", padx=6)
        self.detect_button = ttk.Button(right, text="Detect available GPUs", command=self.detect)
        self.detect_button.pack(anchor="w", pady=4)
        ttk.Checkbutton(
            right, text="Allow verified llama.cpp runtime download", variable=self.allow_download
        ).pack(anchor="w", pady=6)
        self.device_list = tk.Listbox(right, selectmode="multiple", exportselection=False, height=4)
        self.device_list.pack(fill="x")
        network = ttk.Frame(right)
        network.pack(fill="x", pady=6)
        ttk.Label(
            right,
            text="This computer's private address and port (saved by Approve this computer)",
        ).pack(anchor="w")
        ttk.Combobox(network, textvariable=self.host, values=local_addresses(), width=18).pack(
            side="left", padx=6
        )
        ttk.Entry(network, textvariable=self.port, width=6).pack(side="left")
        ttk.Label(
            right,
            text=(
                "Network groups need an existing private route (LAN or "
                "Tailscale). No router or firewall changes are made. Selected "
                "devices are reserved while the engine runs."
            ),
            wraplength=550,
            style="Muted.TLabel",
        ).pack(fill="x", pady=4)
        actions = ttk.Frame(action_area)
        actions.pack(fill="x", pady=6)
        self.approve_button = ttk.Button(
            actions, text="Approve this computer", command=self.approve
        )
        self.approve_button.pack(side="left")
        self.start_button = ttk.Button(
            actions, text="Configure and Start", command=lambda: self.control("start")
        )
        self.start_button.pack(side="left", padx=6)
        self.withdraw_button = ttk.Button(
            action_area, text="Stop and withdraw this computer", command=self.withdraw
        )
        self.withdraw_button.pack(anchor="w")
        message = ttk.Label(action_area, textvariable=self.message, wraplength=550, padding=(0, 8))
        message.pack(fill="x")
        message.bind(
            "<Configure>", lambda event: message.configure(wraplength=max(100, event.width - 12))
        )
        self.selection()
        self.timer = app.root.after(3000, self.tick)

    def selected(self) -> EngineGroup | None:
        selection = self.table.selection()
        return self.groups.get(selection[0]) if selection else None

    def context_menu(self, event: Any) -> str:
        row = self.table.identify_row(event.y)
        if row:
            self.table.selection_set(row)
            self.table.focus(row)
            self.table.focus_set()
            self.selection()
            self.menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def keyboard_menu(self, _: object = None) -> str:
        if self.selected():
            self.menu.tk_popup(self.table.winfo_rootx() + 24, self.table.winfo_rooty() + 24)
        return "break"

    def selection(self, _: object = None) -> None:
        group = self.selected()
        enabled = group is not None and not self.busy
        leader = group is not None and group.proposal.leader_node_id == self.node_id
        self.approve_button.configure(
            state="normal" if enabled and group and not group.desired_running else "disabled"
        )
        self.start_button.configure(
            state="normal"
            if enabled and leader and group and not group.desired_running and group.group
            else "disabled"
        )
        self.withdraw_button.configure(state="normal" if enabled else "disabled")
        self.delete_button.configure(state="normal" if enabled else "disabled")
        self.menu.entryconfigure(0, state="normal" if enabled else "disabled")
        for button in (self.setup_button, self.refresh_button, self.detect_button):
            button.configure(state="disabled" if self.busy else "normal")
        if group:
            if self.endpoint_group_id != group.proposal.id:
                self.endpoint_group_id = group.proposal.id
                own = next((m for m in group.members if m.node_id == self.node_id), None)
                if own and own.approved and own.host and own.port:
                    self.host.set(own.host)
                    self.port.set(str(own.port))
            states = "; ".join(
                f"{m.name} ({m.owner}): "
                + (
                    "Approved - waiting to start"
                    if m.approved and m.phase == "waiting"
                    else m.phase.capitalize()
                    if m.approved
                    else "Withdrawn"
                    if m.phase == "stopped"
                    else "Owner approval needed"
                )
                + (f" (saved address: {m.host}, port {m.port})" if m.host and m.port else "")
                for m in group.members
            )
            self.detail.set(
                f"{group.proposal.name} ({str(group.proposal.id)[:8]})\n"
                f"{group.proposal.model_name}\n{states}"
            )
        else:
            self.endpoint_group_id = None
            self.detail.set("Choose a setup to review participation.")

    def client(self) -> WorkerClient:
        account = self.app.identity
        if not account:
            raise ValueError("Connect this computer first")
        return WorkerClient(account.get("origin", API_ORIGIN), account["token"])

    def deliver(self, action: Callable[[], None]) -> None:
        self.app.event("shared_update", apply=action)

    def task(
        self,
        action: Callable[[], Any],
        done: Callable[[Any], None],
        *,
        pending: str,
        failure: str = "",
    ) -> None:
        if self.busy or self.app.closing:
            if not self.app.closing:
                self.message.set(
                    "An operation is already in progress. Please wait, then try again."
                )
            return
        self.busy = True
        self.revision += 1
        self.message.set(pending)
        self.selection()
        self.cancel.clear()
        self.progress.start(12)

        def work() -> None:
            try:
                result = action()
            except Exception as error:
                if isinstance(error, HTTPError):
                    text = {
                        403: "This computer or account does not have permission for this action.",
                        404: "Setup is unavailable. Check workspace membership and "
                        "that the coordinator supports this worker.",
                        409: "Setup changed or a computer is unavailable. Refresh, "
                        "resume participating workers, and check owner approvals.",
                        422: "Check the selected devices and this computer's private address. "
                        "Single-computer groups require at least two GPUs.",
                    }.get(
                        error.code, "The coordinator could not complete setup. Refresh and retry."
                    )
                else:
                    text = (
                        str(error)
                        if isinstance(error, (OSError, ValueError))
                        else "Shared inference setup failed. "
                        "Check this computer's engine and retry."
                    )
                self.deliver(lambda: self.finished((failure + " " + text).strip()))
            else:

                def complete() -> None:
                    self.finished()
                    if not self.app.closing:
                        try:
                            done(result)
                        except (ValueError, KeyError, TypeError):
                            self.finished(
                                "The coordinator returned an invalid setup response. "
                                "Refresh and retry."
                            )

                self.deliver(complete)

        self.app.background(work)

    def finished(self, error: str = "") -> None:
        self.busy = False
        self.progress.stop()
        if error:
            self.message.set(error)
            self.stop_notice = ""
        self.selection()

    def tick(self) -> None:
        if self.app.closing:
            return
        self.refresh()
        self.timer = self.app.root.after(5000, self.tick)

    def refresh(self, *, manual: bool = False) -> None:
        if not self.app.identity or self.polling or self.busy or self.app.closing:
            if manual and not self.app.closing:
                self.message.set(
                    "Connect this computer first."
                    if not self.app.identity
                    else "An operation is already in progress. Please wait for it to finish."
                )
            return
        self.polling = True
        if manual:
            self.message.set("Refreshing shared inference setups...")
            self.progress.start(12)
        revision = self.revision
        account = dict(self.app.identity)
        client = self.client()

        def apply(node_id: UUID | None = None, groups: list[EngineGroup] | None = None) -> None:
            self.polling = False
            if revision != self.revision or self.busy or self.app.identity != account:
                return
            if manual and not self.activating and not self.stopping:
                self.progress.stop()
            if node_id is None or groups is None:
                if manual:
                    self.message.set(
                        "Could not refresh shared inference setups. Check the connection and retry."
                    )
                self.unavailable()
            else:
                self.received(node_id, groups)
                if manual:
                    self.message.set(
                        f"Refresh complete. {len(groups)} shared inference setup(s) found."
                    )

        def poll() -> None:
            try:
                raw = client.post_document(PREFIX + "groups", Options())
                if not isinstance(raw, dict):
                    raise ValueError("Invalid setup response")
                groups = [EngineGroup.model_validate(g) for g in raw["groups"]]
                node_id = UUID(raw["node_id"])
                self.deliver(lambda: apply(node_id, groups))
            except Exception:
                self.deliver(apply)

        self.app.background(poll)

    def unavailable(self) -> None:
        self.polling = False
        if monotonic() - self.last_seen >= 30:
            self.message.set(
                "Shared inference disconnected. Resume this computer and refresh to reconnect."
            )
            self.stop_local()

    def received(self, node_id: UUID, groups: list[EngineGroup]) -> None:
        self.polling = False
        if self.app.closing:
            return
        self.last_seen = monotonic()
        self.node_id = node_id
        previous = self.selected()
        selected = self.table.selection()
        self.groups = {str(g.proposal.id): g for g in groups}
        self.table.delete(*self.table.get_children())
        for key, group in self.groups.items():
            own = next(m for m in group.members if m.node_id == node_id)
            state = (
                ("Running" if all(m.phase == "ready" for m in group.members) else "Starting")
                if group.desired_running
                else (
                    "Withdrawn"
                    if not own.approved and own.phase == "stopped"
                    else "Ready to start"
                    if group.group
                    else "Approved; awaiting owners"
                    if own.approved
                    else "Awaiting your approval"
                )
            )
            self.table.insert("", "end", iid=key, values=(group.proposal.name, state))
        if selected and selected[0] in self.groups:
            self.table.selection_set(selected[0])
        elif groups:
            self.table.selection_set(str(groups[0].proposal.id))
        self.selection()
        current = self.selected()
        if hasattr(self.app, "activity"):
            self.app.activity.shared_groups(node_id, groups)
        if (
            previous
            and current
            and previous.proposal.id == current.proposal.id
            and not current.desired_running
            and any(m.node_id == node_id and m.approved for m in current.members)
            and self.message.get() == approval_message(previous)
        ):
            self.message.set(approval_message(current))
        if self.message.get() == "Connect this computer, then set up a shared local model.":
            self.message.set(
                "Select a setup to approve participation. Right-click a setup to delete it."
                if groups
                else "No shared inference setups. Select Set up Shared Inference to begin."
            )
        account = self.app.identity or {}
        if self.engine:
            current = self.groups.get(str(self.engine.group.proposal.id))
            valid = (
                current
                and current.desired_running
                and current.group == self.engine.group.group
                and current.generation == self.engine.group.generation
                and load_consent(self.app.folder, current, account.get("credential_id", ""))
            )
            if not valid or (self.ready and not self.engine.alive):
                if valid:
                    failed = self.engine.group
                    self.app.background(lambda: self.report_failure(failed))
                self.stop_local()
            return
        if self.stopping or self.activating or self.suspended:
            return
        self.pending = None
        for group in groups:
            if (
                group.proposal.id in self.revoked
                or not group.desired_running
                or self.failed_run
                == (
                    group.proposal.id,
                    group.generation,
                )
            ):
                continue
            consent = load_consent(self.app.folder, group, account.get("credential_id", ""))
            if not consent:
                continue
            # Peers expose their approved TLS endpoints first; leader loads only when ready.
            if node_id == group.proposal.leader_node_id and any(
                m.node_id != node_id and m.phase != "ready" for m in group.members
            ):
                self.message.set(
                    "Waiting for participating computers to finish their current work and start."
                )
                continue
            self.pending = group
            self.app.settings_restart_pending = False
            if self.app.controller and self.app.controller.running:
                self.app.controller.maintenance_event.set()
                self.message.set("Finishing current work before starting shared inference...")
            else:
                self.activate(group, consent)
            break

    def worker_stopped(self) -> bool:
        if self.pending and not self.app.closing and not self.engine:
            group = self.pending
            consent = load_consent(
                self.app.folder, group, (self.app.identity or {}).get("credential_id", "")
            )
            if consent:
                self.activate(group, consent)
                return True
        return self.activating or self.stopping

    def activate(self, group: EngineGroup, consent: LocalEngineConsent) -> None:
        if self.activating or self.stopping or self.app.closing:
            return
        self.pending = None
        self.activating = True
        self.message.set("Configuring llama.cpp and loading the approved shared model...")
        self.progress.start(12)
        client = self.client()

        def work() -> None:
            engine = None
            try:
                client.post_document(
                    PREFIX + "report",
                    EngineReport(
                        group_id=group.proposal.id, generation=group.generation, phase="starting"
                    ),
                )
                runtime = existing(self.app.folder, consent.backend)
                if runtime is None:
                    raise ValueError("Detect available GPUs and approve the runtime locally first")
                engine = Engine(self.app.folder, consent, runtime, group)
                self.engine = engine
                if self.app.closing or self.suspended or group.proposal.id in self.revoked:
                    raise ValueError("Shared engine startup cancelled")
                engine.start()
                client.post_document(
                    PREFIX + "report",
                    EngineReport(
                        group_id=group.proposal.id, generation=group.generation, phase="ready"
                    ),
                )
                self.deliver(self.started)
            except Exception as error:
                if engine:
                    engine.stop()
                self.report_failure(group)
                detail = str(error) if isinstance(error, ValueError) else ""
                self.deliver(lambda: self.activation_failed(group, detail))

        self.app.background(work)

    def started(self) -> None:
        self.activating = False
        self.progress.stop()
        if self.app.closing or self.stopping or not self.engine or self.engine.stop_event.is_set():
            self.stop_local()
            return
        self.ready = True
        self.message.set(
            "Shared engine ready. Select this group in Command Center → Distributed Jobs."
        )
        self.app.start()

    def report_failure(self, group: EngineGroup) -> None:
        with suppress(Exception):
            self.client().post_document(
                PREFIX + "report",
                EngineReport(
                    group_id=group.proposal.id,
                    generation=group.generation,
                    phase="error",
                    error_code="engine_failed",
                ),
            )

    def activation_failed(self, group: EngineGroup, detail: str = "") -> None:
        self.engine = None
        self.ready = self.activating = False
        self.progress.stop()
        self.failed_run = (group.proposal.id, group.generation)
        self.message.set(
            (detail + ". " if detail else "The shared engine could not start. ")
            + "Check model compatibility, "
            "free memory, backend drivers and private peer routes. Refresh, "
            "then Configure and Start to retry."
        )
        if not self.app.closing:
            self.app.start()

    def stop_local(self, *, resume: bool = True) -> None:
        self.pending = None
        if self.stopping or not self.engine:
            return
        self.stopping = True
        self.ready = False
        engine, controller = self.engine, self.app.controller
        engine.stop_event.set()
        if controller:
            controller.stop()

        def stop() -> None:
            if controller and controller.thread:
                controller.thread.join(30)
            engine.stop()
            with suppress(Exception):
                self.client().post_document(
                    PREFIX + "report",
                    EngineReport(
                        group_id=engine.group.proposal.id,
                        generation=engine.group.generation,
                        phase="stopped",
                    ),
                )
            self.deliver(lambda: self.stopped(resume))

        self.app.background(stop)

    def stopped(self, resume: bool) -> None:
        self.engine = None
        self.ready = self.activating = self.stopping = False
        if not self.busy:
            self.progress.stop()
        if self.stop_notice and not self.busy:
            self.message.set(self.stop_notice)
            self.stop_notice = ""
        if resume and not self.app.closing:
            self.app.start()

    def withdraw(self) -> None:
        group = self.selected()
        if not group:
            self.message.set("Select a shared inference setup first.")
            return
        self.control("withdraw")

    def revoke_local(self, group: EngineGroup) -> None:
        self.revoked.add(group.proposal.id)
        if self.pending and self.pending.proposal.id == group.proposal.id:
            self.pending = None
        if self.engine and self.engine.group.proposal.id == group.proposal.id:
            self.stop_local()

    def updated(self, raw: Any, message: str) -> None:
        group = EngineGroup.model_validate(raw)
        self.groups[str(group.proposal.id)] = group
        if self.node_id:
            self.received(self.node_id, list(self.groups.values()))
        self.message.set(message)

    def delete(self) -> None:
        group = self.selected()
        if not group:
            self.message.set("Select a shared inference setup first.")
            return
        if self.busy:
            self.message.set("An operation is already in progress. Please wait, then try again.")
            return
        leader = group.proposal.leader_node_id == self.node_id
        scope = (
            "This deletes the setup for all participating computers."
            if leader
            else "This removes the setup from this computer and withdraws its approval. "
            "Other computers keep their setup."
        )
        if not messagebox.askyesno(
            "Delete shared inference setup",
            f'Delete "{group.proposal.name}" ({str(group.proposal.id)[:8]})?\n'
            f"Model: {group.proposal.model_name}\n\n{scope}\n\n"
            "The shared engine will stop and active distributed jobs may be interrupted. "
            "Installed model files and job history are retained.",
            parent=self.app.root,
        ):
            self.message.set("Deletion cancelled. The setup is unchanged.")
            return
        self.revoke_local(group)

        def remove() -> object:
            consent_path(self.app.folder, group.proposal.id).unlink(missing_ok=True)
            return self.client().post_document(
                PREFIX + "delete", EngineDelete(group_id=group.proposal.id)
            )

        def removed(raw: Any) -> None:
            if not isinstance(raw, dict) or raw.get("removed") is not True:
                self.message.set("Deletion was not confirmed. Refresh and retry.")
                return
            self.local_models.pop(group.proposal.id, None)
            self.groups.pop(str(group.proposal.id), None)
            if self.node_id:
                self.received(self.node_id, list(self.groups.values()))
            notice = (
                f'Setup deleted: "{group.proposal.name}" ({str(group.proposal.id)[:8]}). '
                "Installed models and job history are retained."
                if raw.get("scope") == "setup"
                else f'Setup "{group.proposal.name}" ({str(group.proposal.id)[:8]}) removed '
                "from this computer. Its participation approval is withdrawn."
            )
            if self.stopping:
                self.stop_notice = notice
                notice += " Stopping this computer's shared engine..."
            self.message.set(notice)

        self.task(
            remove,
            removed,
            pending="Deleting shared inference setup...",
            failure="Participation stopped locally; deletion was not confirmed. Retry deletion.",
        )

    def control(self, action: str) -> None:
        group = self.selected()
        if not group:
            self.message.set("Select a shared inference setup first.")
            return
        if self.busy:
            self.message.set("An operation is already in progress. Please wait, then try again.")
            return
        if action == "start":
            self.suspended = False
            consent = load_consent(
                self.app.folder, group, (self.app.identity or {}).get("credential_id", "")
            )
            if not consent:
                self.message.set("Approve this computer locally before starting this group.")
                return
            try:
                endpoint_matches = (
                    private_address(self.host.get()) == consent.host
                    and int(self.port.get()) == consent.port
                )
            except ValueError:
                endpoint_matches = False
            if not endpoint_matches:
                self.message.set(
                    "The address or port has changed. Click Approve this computer to save "
                    "your selection before starting. "
                    f"Saved address: {consent.host}, port {consent.port}."
                )
                return
        if action == "withdraw":
            self.revoke_local(group)

        def send() -> object:
            if action == "withdraw":
                consent_path(self.app.folder, group.proposal.id).unlink(missing_ok=True)
            return self.client().post_document(
                PREFIX + "control", EngineAction(group_id=group.proposal.id, action=action)
            )

        def done(raw: Any) -> None:
            label = f'"{group.proposal.name}" ({str(group.proposal.id)[:8]})'
            notice = {
                "withdraw": f"Approval withdrawn for {label}. "
                "This computer is no longer participating.",
                "start": f"Start requested for {label}. Waiting for participating computers "
                "to start the engine...",
                "stop": f"Stop requested for {label}. Participating computers "
                "are stopping the shared engine...",
            }[action]
            if action == "withdraw" and self.stopping:
                self.stop_notice = notice
                notice += " Stopping this computer's shared engine..."
            self.updated(raw, notice)

        self.task(
            send,
            done,
            pending={
                "withdraw": "Stopping shared inference and withdrawing this computer's approval...",
                "start": "Requesting shared inference startup...",
                "stop": "Requesting shared inference shutdown...",
            }[action],
            failure="Local participation stopped; withdrawal was not confirmed. Retry withdrawal."
            if action == "withdraw"
            else "",
        )

    def detect(self) -> None:
        backend, allowed = self.backend.get(), self.allow_download.get()

        def probe() -> list[EngineDevice]:
            runtime = install(
                self.app.folder,
                backend,
                allowed,
                self.cancel,
                lambda stage, n, total: self.deliver(lambda: self.message.set(stage)),
            )
            return devices(runtime)

        def show(values: list[EngineDevice]) -> None:
            self.available, self.detected_backend = values, backend
            self.device_list.delete(0, "end")
            for device in values:
                self.device_list.insert("end", f"{device.id}: {device.name}")
            self.message.set("Choose this computer's participating devices, then approve.")

        self.task(probe, show, pending="Detecting this computer's available devices...")

    def approve(self) -> None:
        group = self.selected()
        if not group or not self.node_id or not self.app.identity:
            self.message.set("Connect this computer and select a shared inference setup first.")
            return
        if self.busy:
            self.message.set("An operation is already in progress. Please wait, then try again.")
            return
        self.suspended = False
        selected = [self.available[int(i)] for i in self.device_list.curselection()]  # type: ignore[no-untyped-call]
        if not selected or self.detected_backend != self.backend.get():
            self.message.set("Detect and select devices for the chosen backend first.")
            return
        path = None
        if self.node_id == group.proposal.leader_node_id:
            path = self.local_models.get(group.proposal.id) or filedialog.askopenfilename(
                title="Choose the installed GGUF model", filetypes=[("GGUF models", "*.gguf")]
            )
            if not path:
                self.message.set("Approval cancelled. Choose an installed GGUF model to continue.")
                return
        try:
            consent = LocalEngineConsent(
                proposal=group.proposal,
                node_id=self.node_id,
                credential_id=UUID(self.app.identity["credential_id"]),
                devices=selected,
                backend=self.backend.get(),
                host=self.host.get(),
                port=int(self.port.get()),
                model_path=str(gguf(Path(path))) if path else None,
                threads=self.app.settings.cpu_cores,
            )
            if group.proposal.mode == "single_host" and (
                len(selected) < 2 or any(d.backend == "cpu" for d in selected)
            ):
                raise ValueError("Choose at least two GPUs, or invite another computer.")
            if (
                self.node_id != group.proposal.leader_node_id
                and ipaddress.ip_address(consent.host).is_loopback
            ):
                raise ValueError("Choose this computer's private network address.")
        except (ValueError, OSError) as error:
            self.message.set(str(error))
            return
        if not messagebox.askyesno(
            "Approve shared inference",
            f"Allow {group.proposal.name} to reserve "
            f"{', '.join(d.id for d in selected)} on this computer?\n\n"
            "The initiating computer can start this exact group until you withdraw. "
            "Model data and inference travel between the approved computers over "
            "authenticated TLS. Only the leader reads the selected local model file. "
            "No host files or shell access are granted.\n\n"
            f"Save this computer's address: {consent.host}, port {consent.port}.",
            parent=self.app.root,
        ):
            self.message.set("Approval cancelled. This computer has not granted new permission.")
            return

        def approve() -> object:
            _, _, certificate = identity(self.app.folder, consent.node_id, group.proposal.id)
            save_consent(self.app.folder, consent)
            return self.client().post_document(
                PREFIX + "approve",
                EngineApproval(
                    group_id=group.proposal.id,
                    devices=selected,
                    host=consent.host,
                    port=consent.port,
                    certificate=certificate,
                ),
            )

        def approved(raw: Any) -> None:
            self.revoked.discard(group.proposal.id)
            result = EngineGroup.model_validate(raw)
            self.updated(result, approval_message(result))

        self.task(approve, approved, pending="Saving this computer's participation approval...")

    def wizard(self) -> None:
        if self.wizard_window and self.wizard_window.winfo_exists():
            self.wizard_window.lift()
            return
        if not self.app.identity:
            self.message.set("Connect this computer first.")
            return
        self.task(
            lambda: self.client().post_document(PREFIX + "options", Options()),
            self.open_wizard,
            pending="Loading available workspaces and computers...",
        )

    def open_wizard(self, raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        self.node_id = UUID(raw["node_id"])
        window = tk.Toplevel(self.app.root)
        self.wizard_window = window
        window.title("Set up Shared Inference")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)

        def close() -> None:
            self.message.set(
                "Setup window closed. Any request already sent will still appear in the list."
                if self.busy
                else "Setup cancelled. No new shared inference setup was created."
            )
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close)
        self.message.set("Choose an installed model, workspace and participating computers.")
        workspaces = {f"{w['name']} ({w['id'][:8]})": UUID(w["id"]) for w in raw["workspaces"]}
        workspace = tk.StringVar(value=next(iter(workspaces), ""))
        name = tk.StringVar(value="Shared local model")
        model = tk.StringVar()
        installed = {
            m.name: m.gguf_path or m.location
            for m in (self.app.scan_result.models if self.app.scan_result else [])
            if m.gguf_path or (Path(m.location).suffix.lower() == ".gguf" and not m.served)
        }
        mode = tk.StringVar(value="GPUs in this computer")
        ttk.Label(frame, text="1. Choose an installed compatible model", style="Title.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            frame,
            text=(
                "Installed GGUF models only. Scan for Local Models to populate "
                "this list, or browse to an existing file."
            ),
            wraplength=580,
        ).pack(anchor="w", pady=6)
        model_box = ttk.Combobox(
            frame, textvariable=model, values=list(installed)[:128], state="readonly", width=65
        )
        model_box.pack(fill="x")

        def browse() -> None:
            selected = filedialog.askopenfilename(
                parent=window, title="Installed GGUF model", filetypes=[("GGUF models", "*.gguf")]
            )
            if selected:
                model_box.configure(values=[selected, *list(installed)[:127]])
                model.set(selected)

        ttk.Button(frame, text="Browse installed model", command=browse).pack(anchor="w", pady=6)
        ttk.Label(frame, text="Workspace").pack(anchor="w")
        workspace_box = ttk.Combobox(
            frame, textvariable=workspace, values=list(workspaces), state="readonly"
        )
        workspace_box.pack(fill="x")
        ttk.Entry(frame, textvariable=name).pack(fill="x", pady=6)
        ttk.Label(frame, text="2. Choose participating computers", style="Title.TLabel").pack(
            anchor="w", pady=(8, 4)
        )
        ttk.Combobox(
            frame,
            textvariable=mode,
            values=list(MODES),
            state="readonly",
            width=32,
        ).pack(anchor="w")
        computers = tk.Listbox(
            frame, selectmode="multiple", exportselection=False, height=6, width=70
        )
        computers.pack(fill="both", expand=True, pady=6)
        candidates: list[dict[str, Any]] = []

        def show_computers(data: Any) -> None:
            if not window.winfo_exists():
                return
            candidates.clear()
            computers.delete(0, "end")
            if isinstance(data, dict):
                for node in data["computers"]:
                    if node["setup_supported"] and node["online"]:
                        candidates.append(node)
                        computers.insert("end", f"{node['name']} · {node['owner']} · {node['os']}")
                        if node["node_id"] == str(self.node_id):
                            computers.selection_set(len(candidates) - 1)
                self.message.set(
                    f"{len(candidates)} compatible computer(s) available. "
                    "Choose participants, then Continue to owner approvals."
                )

        def load_nodes(_: object = None) -> None:
            if workspace.get() in workspaces:
                workspace_id = workspaces[workspace.get()]
                self.task(
                    lambda: self.client().post_document(
                        PREFIX + "options", Options(workspace_id=workspace_id)
                    ),
                    show_computers,
                    pending="Loading available participating computers...",
                )

        workspace_box.bind("<<ComboboxSelected>>", load_nodes)
        ttk.Label(
            frame,
            text="Each owner selects devices and approves on their own worker's "
            "Shared Inference tab. Single computer requires 2+ GPUs. WAN sharing "
            "can be slow; an existing private route is required.",
            wraplength=580,
        ).pack(anchor="w", pady=6)

        def create() -> None:
            try:
                path = gguf(Path(installed.get(model.get(), model.get())))
                plan = EngineCreate(
                    workspace_id=workspaces[workspace.get()],
                    name=name.get(),
                    model_name=model.get()[:100] if model.get() in installed else path.name[:100],
                    mode=MODES[mode.get()],
                    node_ids=[
                        UUID(candidates[int(i)]["node_id"])
                        for i in computers.curselection()  # type: ignore[no-untyped-call]
                    ],
                )
                if self.node_id not in plan.node_ids or (plan.mode == "single_host") != (
                    len(plan.node_ids) == 1
                ):
                    raise ValueError(
                        "Include this computer; choose GPUs in this computer for one "
                        "computer, or a network group for several."
                    )
            except (ValueError, OSError, KeyError) as error:
                messagebox.showerror("Shared inference", str(error), parent=window)
                return

            def created(data: Any) -> None:
                group = EngineGroup.model_validate(data)
                self.local_models[group.proposal.id] = str(path)
                if window.winfo_exists():
                    window.destroy()
                self.message.set(
                    "Setup created. Detect and select this computer's devices, then approve. "
                    "Each other owner approves on their own worker. "
                    "Finally select Configure and Start."
                )
                self.groups[str(group.proposal.id)] = group
                if self.node_id:
                    self.received(self.node_id, list(self.groups.values()))
                self.table.selection_set(str(group.proposal.id))
                self.selection()

            self.task(
                lambda: self.client().post_document(PREFIX + "create", plan),
                created,
                pending="Creating shared inference setup...",
            )

        ttk.Label(frame, textvariable=self.message, wraplength=580).pack(fill="x", pady=6)
        ttk.Button(frame, text="Continue to owner approvals", command=create).pack(
            anchor="e", pady=8
        )
        load_nodes()
