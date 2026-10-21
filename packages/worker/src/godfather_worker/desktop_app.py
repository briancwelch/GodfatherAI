"""Guided Windows/macOS/Linux worker window and native tray integration."""

import asyncio
import json
import logging
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from godfather_model_gateway import ProviderConfig

from godfather_worker.desktop import (
    WEB_ORIGIN,
    Contribution,
    Controller,
    Pairing,
    connection_error,
    coordinator_origin,
)
from godfather_worker.desktop_layout import content_frame
from godfather_worker.discovery import discover
from godfather_worker.inference import discover_models
from godfather_worker.native_desktop import (
    CredentialStore,
    acquire_lock,
    data_folder,
    login_startup_enabled,
    set_login_startup,
)
from godfather_worker.pairing import await_approval
from godfather_worker.tailscale import detect as detect_tailscale


class Application:
    def __init__(self, root: tk.Tk, folder: Path) -> None:
        self.root, self.folder = root, folder
        self.store = CredentialStore()
        self.events: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self.cancel = threading.Event()
        self.identity: dict[str, str] | None = None
        self.controller: Controller | None = None
        self.pairing_busy = False
        self.closing = False
        self.destroyed = False
        self.timer: str | None = None
        self.tray: Any = None
        self.settings = Contribution()
        self.models: list[str] = []
        self.status = tk.StringVar(value="Loading your saved connection...")
        self.address = tk.StringVar(value=WEB_ORIGIN)
        self.owner = tk.StringVar(value="")
        self.code = tk.StringVar(value="")
        self.inventory = tk.StringVar(value="Checking existing local AI models...")
        self.hardware = tk.StringVar(value="")
        self.inference = tk.BooleanVar(value=False)
        self.account_connections = tk.BooleanVar(value=False)
        self.data_image = tk.StringVar(value="")
        self.image_endpoint = tk.StringVar(value="")
        self.image_models = tk.StringVar(value="")
        self.cpu, self.ram = tk.StringVar(value="1"), tk.StringVar(value="2")
        self.shared = tk.BooleanVar(value=False)
        self.owners, self.workspaces = tk.StringVar(), tk.StringVar()
        self.autostart = tk.BooleanVar(value=False)
        root.title("Consigliere — The Godfather AI")
        root.configure(background="#F4F8FC")
        self.app_icon = tk.PhotoImage(
            file=str(Path(__file__).parent / "assets/consigliere.png")
        ).subsample(16)
        root.iconphoto(True, self.app_icon)
        self.network = tk.StringVar(value="Checking optional Tailscale connection…")
        self.network_checking = False
        self.network_timer: str | None = None
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#F4F8FC")
        style.configure("TLabelframe", background="#F4F8FC", bordercolor="#D4DFE9")
        style.configure("TLabelframe.Label", background="#F4F8FC", foreground="#52677D")
        style.configure("TButton", padding=(14, 10), foreground="#1468CC", background="#F4F8FC")
        style.map("TButton", background=[("active", "#E1EFF8")])
        style.configure("TCheckbutton", background="#F4F8FC", foreground="#14283D", padding=6)
        style.configure("TNotebook", background="#F4F8FC", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 10), background="#E8F0F7")
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#FFFFFF")],
            foreground=[("selected", "#087F8C")],
        )
        header = tk.Frame(root, background="#14283D", padx=16, pady=14)
        header.pack(fill="x")
        tk.Label(
            header,
            text="GF",
            background="#14283D",
            foreground="#58D5DE",
            font=("Segoe UI", 16, "bold"),
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
        ).pack(side="left")
        tk.Label(
            header,
            text="Consigliere",
            background="#14283D",
            foreground="#58D5DE",
            font=("Segoe UI", 21, "bold"),
            padx=14,
        ).pack(side="left")
        tk.Label(
            header,
            text="THE GODFATHER AI",
            background="#14283D",
            foreground="#F4F8FC",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        ribbon = ttk.Frame(root, padding=(12, 8))
        ribbon.pack(fill="x")
        connection_commands = ttk.LabelFrame(ribbon, text="CONNECTION", padding=6)
        connection_commands.pack(side="left", fill="y")
        execution_commands = ttk.LabelFrame(ribbon, text="CONTRIBUTION", padding=6)
        execution_commands.pack(side="left", fill="y", padx=8)
        settings_commands = ttk.LabelFrame(ribbon, text="COMPUTER", padding=6)
        settings_commands.pack(side="left", fill="y")
        ttk.Button(settings_commands, text="Projects", command=self.projects).pack(side="left")
        ttk.Button(settings_commands, text="Settings", command=self.advanced).pack(
            side="left", padx=4
        )
        footer = ttk.Frame(root, padding=(16, 8))
        footer.pack(side="bottom", fill="x")
        ttk.Label(
            footer, text="The Godfather AI  /  Consigliere  /  Owner-controlled contribution"
        ).pack(anchor="w")
        style.configure("TLabel", background="#F4F8FC", foreground="#14283D")
        frame = content_frame(root)
        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True)
        connection = ttk.Frame(notebook, padding=16)
        models = ttk.Frame(notebook, padding=16)
        notebook.add(connection, text="Connection")
        notebook.add(models, text="Models & API connections")
        frame = connection
        ttk.Label(
            frame, textvariable=self.status, wraplength=490, font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(14, 6))
        ttk.Label(frame, textvariable=self.owner, wraplength=490).pack(anchor="w")
        ttk.Label(frame, text="Command Center address").pack(anchor="w", pady=(14, 4))
        self.address_entry = ttk.Entry(frame, textvariable=self.address, width=55)
        self.address_entry.pack(fill="x")
        self.connect_button = ttk.Button(
            connection_commands, text="Connect", command=self.connect, state="disabled"
        )
        self.connect_button.pack(side="left")
        ttk.Label(frame, textvariable=self.code, wraplength=490).pack(anchor="w")
        ttk.Checkbutton(
            models,
            text="Allow my existing local AI models",
            variable=self.inference,
            command=self.apply_models,
        ).pack(anchor="w", pady=(12, 4))
        ttk.Label(models, textvariable=self.inventory, wraplength=490).pack(anchor="w")
        ttk.Checkbutton(
            models,
            text="Use API connections from my account",
            variable=self.account_connections,
            command=self.apply_models,
        ).pack(anchor="w", pady=6)
        ttk.Label(
            models,
            text="Manage keys in Account settings. Add project access below.",
            wraplength=490,
        ).pack(anchor="w", pady=4)
        actions = execution_commands
        self.resume_button = ttk.Button(
            actions, text="Resume", command=self.start, state="disabled"
        )
        self.resume_button.pack(side="left", fill="x", expand=True)
        self.pause_button = ttk.Button(actions, text="Pause", command=self.pause, state="disabled")
        self.pause_button.pack(side="left", padx=8, fill="x", expand=True)
        ttk.Button(frame, text="Open Command Center", command=self.open_center).pack(
            fill="x", pady=(0, 10)
        )
        ttk.Label(frame, text="NETWORK", font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(16, 4)
        )
        ttk.Label(frame, textvariable=self.network, wraplength=490).pack(anchor="w")
        ttk.Label(
            frame,
            text="Private routes use your existing system routing and DNS. "
            "No Tailscale login or settings changes are made.",
            wraplength=490,
        ).pack(anchor="w", pady=6)
        ttk.Button(frame, text="Refresh network", command=self.refresh_network).pack(
            anchor="w", pady=6
        )
        ttk.Label(
            frame,
            text="Closing this window keeps the worker in the tray. Use Quit to exit.",
            wraplength=490,
        ).pack(anchor="w", pady=(12, 0))
        root.protocol("WM_DELETE_WINDOW", self.hide)
        self.setup_tray()
        self.background(self.load)
        self.refresh_network()
        self.timer = root.after(100, self.pump)

    def refresh_network(self) -> None:
        if self.network_timer:
            self.root.after_cancel(self.network_timer)
            self.network_timer = None
        if not self.closing:
            self.network_timer = self.root.after(30000, self.refresh_network)
        if not self.network_checking and not self.closing:
            self.network_checking = True
            self.background(lambda: self.event("network", message=detect_tailscale().message))

    def event(self, name: str, **values: Any) -> None:
        self.events.put((name, values))

    def background(self, action: Callable[[], None]) -> None:
        def work() -> None:
            try:
                action()
            except Exception as error:
                message = str(error) if isinstance(error, TimeoutError) else connection_error(error)
                self.event("error", message=message)

        threading.Thread(target=work, daemon=True).start()

    def setup_tray(self) -> None:
        try:
            import pystray  # type: ignore[import-untyped]
            from PIL import Image, ImageDraw

            icon = Image.new("RGB", (64, 64), "#14283D")
            draw = ImageDraw.Draw(icon)
            draw.rounded_rectangle((10, 10, 54, 54), radius=10, outline="#58D5DE", width=4)
            draw.line((22, 25, 42, 25, 42, 40, 33, 40), fill="white", width=5)

            def item(label: str, event: str) -> Any:
                return pystray.MenuItem(label, lambda *_: self.event(event))

            self.tray = pystray.Icon(
                "godfather-worker",
                icon,
                "Consigliere — The Godfather AI",
                pystray.Menu(
                    pystray.MenuItem(
                        "Show Consigliere", lambda *_: self.event("show"), default=True
                    ),
                    item("Open Command Center", "open"),
                    item("Resume", "resume"),
                    item("Pause", "pause"),
                    item("Quit", "quit"),
                ),
            )
            self.tray.run_detached()
        except Exception:
            # A missing Linux desktop tray must never leave an invisible worker.
            self.tray = None

    def load(self) -> None:
        saved = self.store.read()
        identity = json.loads(saved) if saved else None
        path = self.folder / "settings.json"
        settings = (
            Contribution.model_validate_json(path.read_text()) if path.exists() else Contribution()
        )
        deployments = asyncio.run(
            discover_models([ProviderConfig(id="local-ollama", provider="ollama")])
        )
        self.event(
            "loaded",
            identity=identity,
            settings=settings,
            advertisement=discover(),
            models=[m.identifier for m in deployments],
            startup=login_startup_enabled(),
        )

    def connect(self) -> None:
        if self.identity:
            return
        if self.pairing_busy:
            self.cancel.set()
            self.status.set("Cancelling connection...")
            return
        try:
            origin = coordinator_origin(self.address.get())
        except ValueError as error:
            messagebox.showerror("Coordinator address", str(error))
            return
        self.address.set(origin)
        pairing = Pairing(origin=origin)
        self.cancel = threading.Event()
        self.pairing_busy = True
        self.connect_button.configure(text="Cancel connection", state="normal")
        self.address_entry.configure(state="disabled")
        self.code.set("Match this code in your browser: " + pairing.challenge[:12].upper())
        self.status.set("Approve this computer in your browser. Connecting automatically...")

        def exchange() -> None:
            try:
                identity = await_approval(pairing, self.store, self.cancel)
                if identity:
                    self.event("identity", identity=identity)
            finally:
                self.event("pairing_finished")

        self.background(exchange)
        webbrowser.open(pairing.browser_url)

    def start(self) -> None:
        if not self.identity or self.closing or (self.controller and self.controller.running):
            return
        try:
            self.settings = self.settings.model_copy(
                update={
                    "inference": self.inference.get(),
                    "account_providers": self.account_connections.get(),
                }
            )
            if self.settings.inference and not self.models:
                raise ValueError(
                    "No local models found. Open your local AI runtime and restart the worker."
                )
            self.controller = Controller(self.identity, self.folder, self.event)
            self.controller.start(self.settings)
            self.status.set("Connecting...")
            self.resume_button.configure(state="disabled")
            self.pause_button.configure(state="normal")
        except (ValueError, OSError) as error:
            messagebox.showerror("Worker settings", str(error))

    def apply_models(self) -> None:
        if self.controller and self.controller.running:
            self.inference.set(self.settings.inference)
            self.account_connections.set(self.settings.account_providers)
            messagebox.showinfo(
                "Pause first", "Pause the worker before changing contributions, then Resume."
            )

    def pause(self) -> None:
        if self.controller and self.controller.running:
            self.controller.stop()
            self.status.set("Pausing safely...")

    def open_center(self) -> None:
        # Saved credentials always use their bound origin, regardless of textbox edits.
        webbrowser.open(coordinator_origin((self.identity or {}).get("origin", self.address.get())))

    def projects(self) -> None:
        if not self.identity:
            messagebox.showinfo(
                "Connect first", "Connect this computer before adding a coding project."
            )
            return
        from godfather_worker.coding_projects import Projects

        Projects(self)

    def advanced(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Worker settings")
        frame = content_frame(window, maximum_width=740)
        ttk.Label(frame, textvariable=self.hardware, wraplength=470).pack(anchor="w")
        for label, variable in (
            ("CPU scheduling cores", self.cpu),
            ("RAM scheduling GiB", self.ram),
        ):
            ttk.Label(frame, text=label).pack(anchor="w", pady=(10, 0))
            ttk.Entry(frame, textvariable=variable).pack(fill="x")
        ttk.Label(
            frame,
            text="Scheduling limits do not enforce host or Ollama resource usage.",
            wraplength=470,
        ).pack(anchor="w", pady=8)
        ttk.Checkbutton(frame, text="Accept explicitly shared work", variable=self.shared).pack(
            anchor="w"
        )
        for label, variable in (
            ("Allowed owner IDs (comma separated)", self.owners),
            ("Allowed workspace IDs (comma separated)", self.workspaces),
        ):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=variable, width=52).pack(fill="x")
        for label, variable in (
            ("Analytics/reporting: installed Python image digest (blank: off)", self.data_image),
            ("Local image API URL (blank: off)", self.image_endpoint),
            ("Permitted installed image model names (comma separated)", self.image_models),
        ):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=variable, width=52).pack(fill="x")
        ttk.Label(
            frame,
            text=(
                "Saving enables these workloads on this computer. Data runs in a networkless "
                "512 MiB container. Nothing is downloaded."
            ),
            wraplength=470,
        ).pack(anchor="w")
        ttk.Checkbutton(
            frame, text="Start at login", variable=self.autostart, command=self.startup
        ).pack(anchor="w", pady=10)

        def save() -> None:
            if self.controller and self.controller.running:
                messagebox.showinfo("Pause first", "Pause the worker before saving settings.")
                return
            try:
                self.settings = Contribution(
                    workloads={
                        "image": self.data_image.get().strip() or None,
                        "images": {
                            "url": self.image_endpoint.get().strip(),
                            "models": [
                                m.strip() for m in self.image_models.get().split(",") if m.strip()
                            ],
                        }
                        if self.image_endpoint.get().strip()
                        else None,
                    }
                    if self.data_image.get().strip() or self.image_endpoint.get().strip()
                    else None,
                    repositories=self.settings.repositories,
                    cpu_cores=int(self.cpu.get()),
                    ram_gib=int(self.ram.get()),
                    inference=self.inference.get(),
                    account_providers=self.account_connections.get(),
                    shared=self.shared.get(),
                    allowed_owner_ids=[
                        s.strip() for s in self.owners.get().split(",") if s.strip()
                    ],
                    allowed_workspace_ids=[
                        s.strip() for s in self.workspaces.get().split(",") if s.strip()
                    ],
                )
                if self.settings.shared and not (
                    self.settings.allowed_owner_ids and self.settings.allowed_workspace_ids
                ):
                    raise ValueError("Shared work needs explicit owner and workspace scopes.")
                from godfather_worker.desktop import save_settings

                save_settings(self.folder / "settings.json", self.settings)
                window.destroy()
            except (ValueError, OSError):
                messagebox.showerror("Check settings", "Enter valid capacity and sharing IDs.")

        ttk.Button(frame, text="Save", command=save).pack(anchor="w")
        ttk.Button(frame, text="Disconnect this computer...", command=self.forget).pack(
            anchor="w", pady=10
        )

    def startup(self) -> None:
        try:
            set_login_startup(self.autostart.get())
        except (ValueError, OSError) as error:
            self.autostart.set(False)
            messagebox.showerror("Start at login", str(error))

    def forget(self) -> None:
        if self.pairing_busy or (self.controller and self.controller.running):
            messagebox.showinfo(
                "Pause first", "Pause and wait for the worker to stop before disconnecting."
            )
            return
        if not messagebox.askyesno(
            "Disconnect",
            "Remove this computer's local connection? Also revoke its credential "
            "in Command Center to end remote authorization.",
        ):
            return
        try:
            self.store.delete()
            self.identity = None
            self.owner.set("")
            self.address_entry.configure(state="normal")
            self.connect_button.configure(state="normal")
            self.resume_button.configure(state="disabled")
            self.status.set("Disconnected. Ready to connect.")
        except OSError:
            messagebox.showerror(
                "Disconnect", "Unlock the operating system credential store and try again."
            )

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def hide(self) -> None:
        if self.tray:
            self.root.withdraw()
        else:
            self.quit()

    def quit(self) -> None:
        if self.network_timer:
            self.root.after_cancel(self.network_timer)
            self.network_timer = None
        if self.closing:
            return
        self.closing = True
        self.cancel.set()
        self.pause()
        self.await_close()

    def await_close(self) -> None:
        if self.pairing_busy or (self.controller and self.controller.running):
            self.root.after(100, self.await_close)
        else:
            if self.tray:
                self.tray.visible = False
                self.tray.stop()
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None
            self.destroyed = True
            self.root.destroy()

    def show_identity(self, identity: dict[str, str]) -> None:
        self.identity = identity
        # Older private Mac enrollments keep their transport until explicitly paired again.
        self.address.set(identity.get("origin", WEB_ORIGIN))
        self.address_entry.configure(state="disabled")
        self.connect_button.configure(state="disabled")
        self.owner.set("Account: " + identity.get("owner", "your saved account"))
        self.code.set("")
        if not self.cancel.is_set():
            self.start()
        else:
            self.status.set("Connection saved. Paused.")
            self.resume_button.configure(state="normal")

    def pump(self) -> None:
        self.timer = None
        while not self.events.empty():
            name, values = self.events.get_nowait()
            if name == "network":
                self.network_checking = False
                self.network.set(values["message"])
            elif name == "loaded":
                self.models = values["models"]
                self.inventory.set(
                    "Local models: "
                    + (
                        ", ".join(self.models)
                        or "None installed. You can use an API connection from Account settings."
                    )
                )
                self.settings = values["settings"]
                self.autostart.set(values["startup"])
                self.inference.set(self.settings.inference)
                self.account_connections.set(self.settings.account_providers)
                workloads = self.settings.workloads
                self.data_image.set(workloads.image or "" if workloads else "")
                self.image_endpoint.set(
                    workloads.images.url if workloads and workloads.images else ""
                )
                self.image_models.set(
                    ",".join(workloads.images.models) if workloads and workloads.images else ""
                )
                self.cpu.set(str(self.settings.cpu_cores))
                self.ram.set(str(self.settings.ram_gib))
                self.shared.set(self.settings.shared)
                self.owners.set(",".join(map(str, self.settings.allowed_owner_ids)))
                self.workspaces.set(",".join(map(str, self.settings.allowed_workspace_ids)))
                ad = values["advertisement"]
                self.hardware.set(
                    f"{ad.os} / {ad.architecture} / {ad.resources.cpu_count} CPU cores"
                )
                if values["identity"]:
                    self.show_identity(values["identity"])
                    if "--login" in sys.argv and self.tray:
                        self.hide()
                else:
                    self.status.set("Ready. Connect to your Command Center.")
                    self.connect_button.configure(state="normal")
            elif name == "identity":
                self.show_identity(values["identity"])
            elif name == "pairing_finished":
                self.pairing_busy = False
                self.connect_button.configure(text="Connect")
                if not self.identity:
                    self.connect_button.configure(state="normal")
                    self.address_entry.configure(state="normal")
                    if self.cancel.is_set():
                        self.status.set("Connection cancelled. Ready to connect.")
                    self.code.set("")
            elif name in ("worker.registered", "worker.heartbeat"):
                self.status.set(
                    "Connected"
                    if values.get("state", "online") != "disabled"
                    else "Node disabled by administrator"
                )
            elif name == "worker.coordinator_unavailable":
                self.status.set("Connection lost. Reconnecting automatically...")
            elif name == "worker.session_busy":
                self.status.set("Waiting for your previous worker session to end safely...")
            elif name == "worker.request_refused":
                self.status.set(
                    "Connection refused. Ask your administrator to check this node's permission."
                )
            elif name == "worker.attempt_started":
                self.status.set("Connected - working on an AI job")
            elif name == "worker.attempt_finished":
                self.status.set("Connected - ready for your next job")
            elif name == "worker.stopped":
                self.resume_button.configure(state="normal" if self.identity else "disabled")
                self.pause_button.configure(state="disabled")
                if self.status.get().startswith("Pausing"):
                    self.status.set("Paused")
            elif name == "error":
                self.status.set(values["message"])
            elif name == "project_update" and not self.closing:
                values["apply"]()
            elif name in ("show", "open", "resume", "pause", "quit"):
                {
                    "show": self.show,
                    "open": self.open_center,
                    "resume": self.start,
                    "pause": self.pause,
                    "quit": self.quit,
                }[name]()
                if self.destroyed:
                    return
            elif name in (
                "worker.unexpected_error",
                "worker.configuration_invalid",
                "worker.invalid_coordinator_response",
            ):
                self.status.set(
                    "Worker could not continue. Check settings or contact your administrator."
                )
            if self.tray:
                self.tray.title = "Consigliere — The Godfather AI: " + self.status.get()[:80]
        if not self.destroyed:
            self.timer = self.root.after(100, self.pump)


def main() -> int:
    if "--install" in sys.argv:
        from godfather_worker.macos_setup import main as install_main

        return install_main()
    logging.disable(logging.CRITICAL)
    root = tk.Tk()
    if "--self-test" in sys.argv:
        # Frozen builds need this fixed source file to pass into a worker sandbox.
        assert Path(__file__).with_name("data_program.py").is_file()
        root.withdraw()
        import pystray
        from PIL import Image

        tray = pystray.Icon("godfather-startup-smoke", Image.new("RGB", (16, 16), "#14283D"))
        tray.run_detached()

        def done() -> None:
            tray.visible = False
            tray.stop()
            root.destroy()

        root.after(200, done)
        root.mainloop()
        return 0
    lock = acquire_lock(data_folder())
    if lock is None:
        root.withdraw()
        messagebox.showinfo(
            "Consigliere — The Godfather AI", "The worker is already open. Use its tray icon."
        )
        root.destroy()
        return 0
    try:
        Application(root, data_folder())
        root.mainloop()
    finally:
        lock.close()
    return 0
