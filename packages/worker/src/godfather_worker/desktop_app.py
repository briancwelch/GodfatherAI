"""Guided Windows/macOS/Linux worker window and native tray integration."""

import asyncio
import json
import logging
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from contextlib import suppress
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
        from godfather_worker import desktop_theme
        from godfather_worker.desktop_layout import window_size

        self.preferences = desktop_theme.load(folder)
        self.settings_dialog: Any = None
        self.project_editor: Any = None
        self.command_images = {
            name: tk.PhotoImage(file=str(Path(__file__).parent / f"assets/command-{name}.png"))
            for name in (
                "providers",
                "workspaces",
                "run",
                "disable",
                "settings",
                "refresh",
                "inspect",
            )
        }
        desktop_theme.apply(ttk.Style(root), self.preferences)
        width = self.preferences.width if self.preferences.remember_size else 1120
        height = self.preferences.height if self.preferences.remember_size else 760
        window_size(root, width, height)
        header = tk.Frame(root, background="#14283D", padx=16, pady=10)
        header.pack(fill="x")
        tk.Label(
            header,
            text="GF",
            background="#14283D",
            foreground="#58D5DE",
            font=("Segoe UI", 12, "bold"),
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
        ).pack(side="left")
        tk.Label(
            header,
            text="Consigliere",
            background="#14283D",
            foreground="#58D5DE",
            font=("Segoe UI", 17, "bold"),
            padx=12,
        ).pack(side="left")
        tk.Label(
            header,
            text="THE GODFATHER AI",
            background="#31465B",
            foreground="#F4F8FC",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=4,
        ).pack(side="left")
        ttk.Style(root).configure("Header.TButton", background="#263D52", foreground="white")
        ttk.Button(header, text="Settings", command=self.advanced, style="Header.TButton").pack(
            side="right"
        )
        menu = tk.Menu(root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Open Command Center", command=self.open_center)
        file_menu.add_command(label="Settings…", command=self.advanced)
        file_menu.add_separator()
        file_menu.add_command(label="Quit Consigliere", command=self.quit)
        menu.add_cascade(label="File", menu=file_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Projects", command=self.projects)
        view_menu.add_command(label="Reset window size", command=lambda: window_size(root))
        menu.add_cascade(label="View", menu=view_menu)
        root.configure(menu=menu)
        ribbon = ttk.Frame(root, padding=(12, 8))
        ribbon.pack(fill="x")

        def group(caption: str) -> ttk.Frame:
            outer = ttk.Frame(ribbon, padding=(0, 0, 12, 0))
            outer.pack(side="left", fill="y")
            commands = ttk.Frame(outer)
            commands.pack(fill="both", expand=True)
            ttk.Label(outer, text=caption, style="RibbonCaption.TLabel").pack(fill="x", pady=(4, 0))
            return commands

        def command(
            parent: ttk.Frame,
            text: str,
            icon: str,
            callback: Callable[[], None],
            disabled: bool = False,
        ) -> ttk.Button:
            button = ttk.Button(
                parent,
                text=text,
                image=self.command_images[icon],
                compound="top",
                command=callback,
                style="Ribbon.TButton",
                state="disabled" if disabled else "normal",
            )
            button.pack(side="left", padx=(0, 4), fill="y")
            return button

        connection_commands = group("CONNECTION")
        self.connect_button = command(
            connection_commands, "Connect", "providers", self.connect, True
        )
        command(connection_commands, "Open Center", "workspaces", self.open_center)
        execution_commands = group("CONTRIBUTION")
        self.resume_button = command(execution_commands, "Resume", "run", self.start, True)
        self.pause_button = command(execution_commands, "Pause", "disable", self.pause, True)
        computer_commands = group("WORKSPACE")
        command(computer_commands, "Projects", "workspaces", self.projects)
        command(computer_commands, "Refresh", "refresh", self.refresh_network)
        ttk.Separator(root).pack(fill="x")
        footer = ttk.Frame(root, padding=(16, 6))
        footer.pack(side="bottom", fill="x")
        ttk.Label(
            footer, text="The Godfather AI · Owner-controlled worker", style="Muted.TLabel"
        ).pack(side="left")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel").pack(side="right")
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(body)
        self.notebook.pack(fill="both", expand=True)
        connection = ttk.Frame(self.notebook, padding=20)
        self.projects_tab = ttk.Frame(self.notebook)
        models = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(connection, text="Connection")
        self.notebook.add(self.projects_tab, text="Projects")
        self.notebook.add(models, text="Models & API connections")
        self.projects_placeholder = ttk.Label(
            self.projects_tab,
            text="Connect this computer, then open Projects to configure your workspace.",
            padding=20,
        )
        self.projects_placeholder.pack(anchor="w")
        self.notebook.bind("<<NotebookTabChanged>>", self.tab_changed)
        connection.columnconfigure(0, weight=3)
        connection.columnconfigure(1, weight=2)
        main = ttk.LabelFrame(connection, text="COMPUTER CONNECTION", padding=16)
        main.grid(row=0, column=0, sticky="new", padx=(0, 16))
        ttk.Label(main, textvariable=self.status, style="Title.TLabel", wraplength=380).pack(
            anchor="w", pady=(0, 8)
        )
        ttk.Label(main, textvariable=self.owner, style="Muted.TLabel", wraplength=380).pack(
            anchor="w"
        )
        ttk.Label(main, text="Command Center address").pack(anchor="w", pady=(18, 5))
        self.address_entry = ttk.Entry(main, textvariable=self.address)
        self.address_entry.pack(fill="x")
        ttk.Label(main, textvariable=self.code, wraplength=380).pack(anchor="w", pady=8)
        network = ttk.LabelFrame(connection, text="NETWORK", padding=16)
        network.grid(row=0, column=1, sticky="new")
        ttk.Label(network, textvariable=self.network, wraplength=280).pack(anchor="w", pady=(0, 12))
        ttk.Label(
            network,
            text=(
                "Authenticated outbound HTTPS. Existing private routes "
                "are preferred when available."
            ),
            style="Muted.TLabel",
            wraplength=280,
        ).pack(anchor="w")
        ttk.Label(connection, textvariable=self.hardware, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=16
        )
        ttk.Label(models, text="Local models", style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(
            models,
            text="Allow my existing local AI models",
            variable=self.inference,
            command=self.apply_models,
        ).pack(anchor="w")
        ttk.Label(models, textvariable=self.inventory, wraplength=650, style="Muted.TLabel").pack(
            anchor="w", pady=8
        )
        ttk.Separator(models).pack(fill="x", pady=16)
        ttk.Label(models, text="Account API connections", style="Title.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        ttk.Checkbutton(
            models,
            text="Use API connections from my account",
            variable=self.account_connections,
            command=self.apply_models,
        ).pack(anchor="w")
        ttk.Label(
            models,
            text=(
                "Manage API keys and computer grants in Command Center. "
                "Google Sign-In remains separate."
            ),
            style="Muted.TLabel",
            wraplength=650,
        ).pack(anchor="w", pady=8)
        ttk.Button(models, text="Open account connections", command=self.open_center).pack(
            anchor="w"
        )
        root.protocol("WM_DELETE_WINDOW", self.close_window)
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

    def tab_changed(self, _: object = None) -> None:
        if self.notebook.select() == str(self.projects_tab):  # type: ignore[no-untyped-call]
            self.projects()

    def projects(self) -> None:
        self.notebook.select(self.projects_tab)  # type: ignore[no-untyped-call]
        if not self.identity:
            return
        if self.project_editor is None:
            from godfather_worker.coding_projects import Projects

            self.projects_placeholder.pack_forget()
            self.project_editor = Projects(self, self.projects_tab)

    def advanced(self) -> None:
        if self.settings_dialog and self.settings_dialog.window.winfo_exists():
            self.settings_dialog.window.lift()
            return
        from godfather_worker.desktop_settings import Settings

        self.settings_dialog = Settings(self)

    def close_window(self) -> None:
        from godfather_worker.desktop_theme import save

        if self.preferences.remember_size:
            self.preferences = self.preferences.model_copy(
                update={
                    "width": max(640, self.root.winfo_width()),
                    "height": max(480, self.root.winfo_height()),
                }
            )
            with suppress(OSError):
                save(self.folder, self.preferences)
        if self.preferences.close_to_tray and self.tray:
            self.hide()
        else:
            self.quit()

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
                    if ("--login" in sys.argv or self.preferences.start_minimized) and self.tray:
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

    def self_test_stage(stage: str) -> None:
        report = os.getenv("GODFATHER_SELF_TEST_REPORT")
        if report and "--self-test" in sys.argv:
            Path(report).write_text(json.dumps({"stage": stage}), encoding="utf-8")

    self_test_stage("before_tk")
    root = tk.Tk()
    if "--self-test" in sys.argv:
        self_test_stage("tk_ready")
        # Frozen builds need this fixed source file to pass into a worker sandbox.
        from godfather_worker.workloads import program_source

        assert program_source().is_file()
        self_test_stage("source_ready")
        root.withdraw()
        import pystray
        from PIL import Image

        tray = pystray.Icon("godfather-startup-smoke", Image.new("RGB", (16, 16), "#14283D"))
        tray.run_detached()
        self_test_stage("tray_started")

        def done() -> None:
            self_test_stage("closing")
            tray.visible = False
            tray.stop()
            root.destroy()

        root.after(200, done)
        root.mainloop()
        self_test_stage("passed")
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
