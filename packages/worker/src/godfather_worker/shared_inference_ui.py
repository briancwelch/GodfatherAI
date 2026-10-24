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
    return sorted(set(addresses), key=lambda value: (not value.startswith("100."), value))


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
        controls = ttk.Frame(parent, padding=(16, 10))
        controls.pack(fill="x")
        ttk.Button(controls, text="Set up Shared Inference", command=self.wizard).pack(side="left")
        ttk.Button(controls, text="Refresh", command=self.refresh).pack(side="left", padx=6)
        message = ttk.Label(parent, textvariable=self.message, wraplength=900, padding=(16, 4))
        message.pack(fill="x")
        message.bind(
            "<Configure>", lambda event: message.configure(wraplength=max(100, event.width - 32))
        )
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
        self.detail = tk.StringVar(value="Choose a group to review participation.")
        ttk.Label(right, textvariable=self.detail, wraplength=550).pack(fill="x", pady=(0, 8))
        row = ttk.Frame(right)
        row.pack(fill="x")
        ttk.Label(row, text="Local engine backend").pack(side="left")
        ttk.Combobox(
            row, textvariable=self.backend, values=variants(), state="readonly", width=10
        ).pack(side="left", padx=6)
        ttk.Button(right, text="Detect available GPUs", command=self.detect).pack(
            anchor="w", pady=4
        )
        ttk.Checkbutton(
            right, text="Allow verified llama.cpp runtime download", variable=self.allow_download
        ).pack(anchor="w", pady=6)
        self.device_list = tk.Listbox(right, selectmode="multiple", exportselection=False, height=4)
        self.device_list.pack(fill="x")
        network = ttk.Frame(right)
        network.pack(fill="x", pady=6)
        ttk.Label(right, text="This computer's private address and port").pack(anchor="w")
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
        self.selection()
        self.timer = app.root.after(3000, self.tick)

    def selected(self) -> EngineGroup | None:
        selection = self.table.selection()
        return self.groups.get(selection[0]) if selection else None

    def selection(self, _: object = None) -> None:
        group = self.selected()
        leader = group is not None and group.proposal.leader_node_id == self.node_id
        self.approve_button.configure(
            state="normal" if group and not group.desired_running else "disabled"
        )
        self.start_button.configure(
            state="normal"
            if leader and group and not group.desired_running and group.group
            else "disabled"
        )
        self.withdraw_button.configure(state="normal" if group else "disabled")
        if group:
            states = "; ".join(
                f"{m.name} ({m.owner}): {m.phase if m.approved else 'owner approval needed'}"
                for m in group.members
            )
            self.detail.set(f"{group.proposal.model_name}\n{states}")

    def client(self) -> WorkerClient:
        account = self.app.identity
        if not account:
            raise ValueError("Connect this computer first")
        return WorkerClient(account.get("origin", API_ORIGIN), account["token"])

    def deliver(self, action: Callable[[], None]) -> None:
        self.app.event("shared_update", apply=action)

    def task(self, action: Callable[[], Any], done: Callable[[Any], None]) -> None:
        if self.busy or self.app.closing:
            return
        self.busy = True
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
                self.deliver(lambda: self.finished(text))
            else:

                def complete() -> None:
                    self.finished()
                    if not self.app.closing:
                        done(result)

                self.deliver(complete)

        self.app.background(work)

    def finished(self, error: str = "") -> None:
        self.busy = False
        self.progress.stop()
        if error:
            self.message.set(error)

    def tick(self) -> None:
        if self.app.closing:
            return
        self.refresh()
        self.timer = self.app.root.after(5000, self.tick)

    def refresh(self) -> None:
        if not self.app.identity or self.polling or self.app.closing:
            return
        self.polling = True
        client = self.client()

        def poll() -> None:
            try:
                raw = client.post_document(PREFIX + "groups", Options())
                if not isinstance(raw, dict):
                    raise ValueError("Invalid setup response")
                groups = [EngineGroup.model_validate(g) for g in raw["groups"]]
                node_id = UUID(raw["node_id"])
                self.deliver(lambda: self.received(node_id, groups))
            except Exception:
                self.deliver(self.unavailable)

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
        selected = self.table.selection()
        self.groups = {str(g.proposal.id): g for g in groups}
        self.table.delete(*self.table.get_children())
        for key, group in self.groups.items():
            state = (
                "Starting / running"
                if group.desired_running
                else "Ready to configure"
                if group.group
                else "Awaiting owners"
            )
            self.table.insert("", "end", iid=key, values=(group.proposal.name, state))
        if selected and selected[0] in self.groups:
            self.table.selection_set(selected[0])
        elif groups:
            self.table.selection_set(str(groups[0].proposal.id))
        self.selection()
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
            if not group.desired_running or self.failed_run == (
                group.proposal.id,
                group.generation,
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
                if self.app.closing or self.suspended:
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
        self.progress.stop()
        if resume and not self.app.closing:
            self.app.start()

    def withdraw(self) -> None:
        group = self.selected()
        if group:
            self.cancel.set()
            consent_path(self.app.folder, group.proposal.id).unlink(missing_ok=True)
            if self.engine and self.engine.group.proposal.id == group.proposal.id:
                self.stop_local()
            self.control("withdraw")

    def control(self, action: str) -> None:
        group = self.selected()
        if not group:
            return
        if action == "start":
            self.suspended = False
            consent = load_consent(
                self.app.folder, group, (self.app.identity or {}).get("credential_id", "")
            )
            if not consent:
                self.message.set("Approve this computer locally before starting this group.")
                return
        self.task(
            lambda: self.client().post_document(
                PREFIX + "control", EngineAction(group_id=group.proposal.id, action=action)
            ),
            lambda _: self.refresh(),
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

        self.task(probe, show)

    def approve(self) -> None:
        group = self.selected()
        if not group or not self.node_id or not self.app.identity:
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
            "No host files or shell access are granted.",
            parent=self.app.root,
        ):
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

        self.task(approve, lambda _: self.refresh())

    def wizard(self) -> None:
        if self.wizard_window and self.wizard_window.winfo_exists():
            self.wizard_window.lift()
            return
        if not self.app.identity:
            self.message.set("Connect this computer first.")
            return
        self.task(
            lambda: self.client().post_document(PREFIX + "options", Options()), self.open_wizard
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

        def load_nodes(_: object = None) -> None:
            if workspace.get() in workspaces:
                workspace_id = workspaces[workspace.get()]
                self.task(
                    lambda: self.client().post_document(
                        PREFIX + "options", Options(workspace_id=workspace_id)
                    ),
                    show_computers,
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
                    "3. Detect and select this computer's devices, then approve. "
                    "Each other owner approves on their own worker. "
                    "Finally select Configure and Start."
                )
                self.refresh()

            self.task(lambda: self.client().post_document(PREFIX + "create", plan), created)

        ttk.Button(frame, text="Continue to owner approvals", command=create).pack(
            anchor="e", pady=8
        )
        load_nodes()
