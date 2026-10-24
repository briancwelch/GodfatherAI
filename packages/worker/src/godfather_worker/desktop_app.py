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
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from godfather_model_gateway import ProviderConfig

from godfather_worker.build_info import worker_version
from godfather_worker.desktop import (
    WEB_ORIGIN,
    Contribution,
    Controller,
    Pairing,
    connection_error,
    coordinator_origin,
    first_run_contribution,
    save_settings,
)
from godfather_worker.discovery import discover
from godfather_worker.local_model_scan import ScanResult, default_roots, local_servers, scan
from godfather_worker.native_desktop import (
    CredentialStore,
    acquire_lock,
    data_folder,
    login_startup_enabled,
    set_login_startup,
)
from godfather_worker.pairing import await_approval
from godfather_worker.project_readiness import PROJECT_ISSUES
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
        self.settings_restart_pending = False
        self.models: list[str] = []
        self.status = tk.StringVar(value="Loading your saved connection...")
        self.connection_state = tk.StringVar(value="DISCONNECTED")
        self.build_version = worker_version()
        self.update_info: dict[str, str] | None = None
        self.update_pending: tuple[Path, str] | None = None
        self.update_checking = False
        self.update_busy = False
        self.update_timer: str | None = None
        self.local_setup_pending = False
        self.local_setup_busy = False
        self.update_status = tk.StringVar(value="Check for updates")
        self.address = tk.StringVar(value=WEB_ORIGIN)
        self.owner = tk.StringVar(value="")
        self.code = tk.StringVar(value="")
        self.inventory = tk.StringVar(value="Select Scan for Local Models to search this computer.")
        self.scan_busy = False
        self.scan_cancel = threading.Event()
        self.scan_result: ScanResult | None = None
        self.scan_roots: list[Path] = []
        self.scan_servers: list[ProviderConfig] = []
        self.scan_status = tk.StringVar(value="Local library paths stay on this computer.")
        self.hardware = tk.StringVar(value="")
        self.inference = tk.BooleanVar(value=False)
        self.model_installation = tk.BooleanVar(value=False)
        self.account_connections = tk.BooleanVar(value=False)
        self.data_image = tk.StringVar(value="")
        self.image_endpoint = tk.StringVar(value="")
        self.image_models = tk.StringVar(value="")
        self.cpu, self.ram = tk.StringVar(value="1"), tk.StringVar(value="2")
        self.shared = tk.BooleanVar(value=False)
        self.contribute = tk.BooleanVar(value=False)
        self.autostart = tk.BooleanVar(value=False)
        root.title("Consigliere — The Godfather AI · " + (self.build_version or "Source checkout"))
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
        self.project_issues: dict[str, str] = {}
        self.projects_checked = False
        self.project_warning = tk.StringVar(value="")
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
        self.connection_badge = tk.Label(
            header,
            textvariable=self.connection_state,
            background="#58431B",
            foreground="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            padx=12,
            pady=6,
        )
        self.connection_badge.pack(side="right", padx=16)
        menu = tk.Menu(root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Open Command Center", command=self.open_center)
        file_menu.add_command(label="Settings…", command=self.advanced)
        file_menu.add_command(label="Check for updates", command=self.check_updates)
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
        self.resume_button = command(execution_commands, "Resume", "run", self.resume, True)
        self.pause_button = command(execution_commands, "Pause", "disable", self.pause, True)
        computer_commands = group("WORKSPACE")
        command(computer_commands, "Projects", "workspaces", self.projects)
        command(computer_commands, "Refresh", "refresh", self.refresh_network)
        ttk.Separator(root).pack(fill="x")
        footer = ttk.Frame(root, padding=(16, 6))
        footer.pack(side="bottom", fill="x")
        ttk.Label(
            footer,
            text="Build " + (self.build_version or "Source checkout"),
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(
            footer, textvariable=self.update_status, command=self.check_updates, width=25
        ).pack(side="left", padx=12)
        connection_status = ttk.Frame(footer)
        connection_status.pack(side="right", fill="x", expand=True)
        # A drawn icon avoids platform-dependent emoji/font rendering.
        self.secure_icon = tk.PhotoImage(width=14, height=16)
        self.secure_icon.put("#087F8C", to=(2, 7, 12, 15))
        for x, y in ((4, 3), (5, 2), (6, 2), (7, 2), (8, 3)):
            self.secure_icon.put("#087F8C", to=(x, y, x + 2, 8))
        self.secure_label = ttk.Label(connection_status, image=self.secure_icon)
        self.secure_label.pack(side="left", padx=(0, 5))
        self.secure_label.pack_forget()
        self.footer_status = ttk.Label(
            connection_status, textvariable=self.status, style="Muted.TLabel", wraplength=240
        )
        self.footer_status.pack(side="left", fill="x", expand=True)
        self.footer_status.bind(
            "<Configure>",
            lambda event: self.footer_status.configure(wraplength=max(1, min(400, event.width))),
        )
        self.update_progress = ttk.Progressbar(connection_status, mode="indeterminate", length=90)
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(body)
        self.notebook.pack(fill="both", expand=True)
        connection = ttk.Frame(self.notebook, padding=20)
        self.projects_tab = ttk.Frame(self.notebook)
        models = ttk.Frame(self.notebook, padding=20)
        self.scan_tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(connection, text="Connection")
        self.notebook.add(self.projects_tab, text="Projects")
        self.notebook.add(models, text="Models & API connections")
        self.notebook.add(self.scan_tab, text="Local model scan")
        self.shared_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.shared_tab, text="Shared Inference")
        from godfather_worker.shared_inference_ui import SharedInference

        self.shared_inference = SharedInference(self, self.shared_tab)
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
        ttk.Label(main, textvariable=self.code, style="Title.TLabel", wraplength=380).pack(
            anchor="w", pady=8
        )
        ttk.Checkbutton(
            main,
            text="Contribute this computer to my workspaces",
            variable=self.contribute,
            command=self.apply_contribution,
        ).pack(anchor="w", pady=(12, 4))
        ttk.Label(
            main,
            text="Use installed local models for ordinary and distributed jobs in your "
            "workspaces. Membership handles sharing, including workspaces you join later. "
            "Turn this off anytime.",
            wraplength=400,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(main, textvariable=self.inventory, wraplength=400, style="Muted.TLabel").pack(
            anchor="w", pady=4
        )
        ttk.Button(main, text="Set up local AI", command=self.setup_local_ai).pack(
            anchor="w", pady=6
        )
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
        self.project_notice = ttk.LabelFrame(network, text="PROJECT NEEDS ATTENTION", padding=12)
        ttk.Label(self.project_notice, textvariable=self.project_warning, wraplength=260).pack(
            anchor="w", fill="x"
        )
        ttk.Button(self.project_notice, text="Open Projects", command=self.projects).pack(
            anchor="w", pady=(8, 0)
        )
        ttk.Label(connection, textvariable=self.hardware, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=16
        )
        ttk.Label(models, text="Local models", style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        self.model_scan_button = ttk.Button(
            models, text="Scan for Local Models", command=self.scan_models
        )
        self.model_scan_button.pack(anchor="w", pady=(0, 8))
        scan_controls = ttk.Frame(self.scan_tab)
        scan_controls.pack(fill="x", pady=(0, 8))
        self.scan_button = ttk.Button(
            scan_controls, text="Scan for Local Models", command=self.scan_models
        )
        self.scan_button.pack(side="left")
        self.cancel_scan_button = ttk.Button(
            scan_controls, text="Cancel scan", command=self.scan_cancel.set, state="disabled"
        )
        self.cancel_scan_button.pack(side="left", padx=6)
        ttk.Button(scan_controls, text="Add folder…", command=self.add_scan_folder).pack(
            side="left", padx=6
        )
        ttk.Button(scan_controls, text="Add local server…", command=self.add_scan_server).pack(
            side="left"
        )
        ttk.Label(
            self.scan_tab, textvariable=self.scan_status, wraplength=850, style="Muted.TLabel"
        ).pack(anchor="w")
        table_frame = ttk.Frame(self.scan_tab)
        table_frame.pack(fill="both", expand=True, pady=8)
        self.scan_table = ttk.Treeview(
            table_frame, columns=("model", "status", "location"), show="headings", height=5
        )
        for column, caption, width in (
            ("model", "Model", 240),
            ("status", "Discovery", 160),
            ("location", "Local location / server", 360),
        ):
            self.scan_table.heading(column, text=caption)
            self.scan_table.column(column, width=width)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.scan_table.yview)
        scroll.pack(side="right", fill="y")
        self.scan_table.configure(yscrollcommand=scroll.set)
        self.scan_table.pack(side="left", fill="both", expand=True)
        self.use_scanned_button = ttk.Button(
            self.scan_tab,
            text="Use detected local text servers",
            command=self.use_scanned_models,
            state="disabled",
        )
        self.use_scanned_button.pack(anchor="w")
        ttk.Label(
            self.scan_tab,
            text="Searches common model libraries and any folders you add, up to 128 results. "
            "Files found on disk need a compatible running server. Use detected servers enables "
            "local chat and streaming; workspace permissions stay separate.",
            wraplength=850,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 8))
        ttk.Checkbutton(
            models,
            text="Allow my existing local AI models",
            variable=self.inference,
            command=self.apply_models,
        ).pack(anchor="w")
        ttk.Checkbutton(
            models,
            text="Allow model downloads from Command Center",
            variable=self.model_installation,
            command=self.apply_models,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            models,
            text=(
                "Enable local AI models above as well. Each download requires confirmation "
                "in Command Center and uses this computer's network and storage. "
                "Use Get started below to set up Ollama on this computer."
            ),
            wraplength=650,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=8)
        ttk.Label(models, textvariable=self.inventory, wraplength=650, style="Muted.TLabel").pack(
            anchor="w", pady=8
        )
        ttk.Button(
            models,
            text="Get started · Download local model from Command Center",
            command=self.setup_local_ai,
        ).pack(anchor="w", pady=8)
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

    def check_updates(self) -> None:
        if (
            self.update_busy
            or self.update_checking
            or self.local_setup_busy
            or not self.identity
            or not self.build_version
        ):
            if not self.identity:
                self.update_status.set("Connect to check updates")
            elif not self.build_version:
                self.update_status.set("Source checkout · No update")
            return
        if self.update_info:
            if (
                self.shared_inference.engine
                or self.shared_inference.activating
                or self.shared_inference.stopping
            ):
                self.update_status.set("Update ready · Stop shared engine")
                return
            if self.preferences.automatic_updates or messagebox.askyesno(
                "Update Available",
                f"Install Consigliere {self.update_info['version']}? "
                "Current work will finish first. Your connection and settings are preserved.",
                parent=self.root,
            ):
                self.update_busy = True
                item = dict(self.update_info)
                origin = self.identity.get("origin", self.address.get())
                self.update_status.set("Downloading update…")
                self.show_update_progress(True)

                def download() -> None:
                    from godfather_worker.updates import download_update

                    try:
                        path = download_update(origin, item, self.folder / "updates")
                        self.event("update_downloaded", path=path, sha256=item["sha256"])
                    except (OSError, ValueError):
                        self.event("update_failed")

                self.background(download)
            return
        self.update_checking = True
        self.update_status.set("Checking for updates…")
        self.show_update_progress(True)
        origin, current = self.identity.get("origin", self.address.get()), self.build_version

        def check() -> None:
            from godfather_worker.updates import available_update

            try:
                self.event("update_checked", item=available_update(origin, current))
            except (OSError, ValueError, KeyError):
                self.event("update_failed")

        self.background(check)

    def show_update_progress(self, active: bool) -> None:
        if active:
            before = (
                self.secure_label
                if self.secure_label.winfo_manager() == "pack"
                else self.footer_status
            )
            self.update_progress.pack(side="left", before=before, padx=(0, 8))
            self.update_progress.start(12)
        else:
            self.update_progress.stop()
            self.update_progress.pack_forget()

    def add_scan_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Choose another local model folder", parent=self.root
        )
        if folder and Path(folder) not in self.scan_roots:
            self.scan_roots.append(Path(folder))
            self.scan_status.set(
                f"{len(self.scan_roots)} additional folder(s). Select Scan for Local Models."
            )

    def add_scan_server(self) -> None:
        port = simpledialog.askinteger(
            "Local model server",
            "Local OpenAI-compatible server port:",
            minvalue=1,
            maxvalue=65535,
            parent=self.root,
        )
        if port is None:
            return
        config = ProviderConfig(
            id=f"local-server-{port}",
            provider="openai_compatible",
            url=f"http://127.0.0.1:{port}/v1",
        )
        if not any(c.id == config.id for c in self.scan_servers):
            if len(self.scan_servers) >= 7:
                self.scan_status.set(
                    "The existing limit is eight local providers including Ollama."
                )
                return
            self.scan_servers.append(config)
        self.scan_status.set("Local server added. Select Scan for Local Models.")

    def scan_models(self) -> None:
        if self.scan_busy or self.closing:
            return
        self.scan_busy = True
        self.notebook.select(self.scan_tab)  # type: ignore[no-untyped-call]
        self.scan_cancel.clear()
        self.scan_button.configure(state="disabled")
        self.model_scan_button.configure(state="disabled")
        self.cancel_scan_button.configure(state="normal")
        self.use_scanned_button.configure(state="disabled")
        self.scan_status.set("Scanning local models…")
        roots = [*default_roots(), *self.scan_roots]
        defaults = local_servers()
        configs = list(
            {
                c.id: c
                for c in [
                    defaults[0],
                    *self.scan_servers,
                    *self.settings.local_providers,
                    *defaults[1:],
                ]
            }.values()
        )[:8]

        def search() -> None:
            try:
                result = scan(
                    roots,
                    configs,
                    self.scan_cancel,
                    lambda message: self.event("scan_progress", message=message),
                )
                self.event("scan_finished", result=result)
            except (OSError, ValueError):
                self.event("scan_failed")

        self.background(search)

    def use_scanned_models(self) -> None:
        if not self.scan_result or self.scan_busy or self.scan_result.cancelled:
            return
        detected = [
            p.model_copy(update={"chat_enabled": True, "stream_enabled": True})
            for p in self.scan_result.providers
            if p.provider == "openai_compatible"
        ]
        providers = list({p.id: p for p in [*self.settings.local_providers, *detected]}.values())
        if len(providers) > 7:
            if not messagebox.askyesno(
                "Local server limit",
                "Only seven text servers plus Ollama fit the existing provider limit. "
                "Replace the saved text-server list with the servers found by this scan? "
                "Current work finishes first.\n\n" + "\n".join(p.url for p in detected),
                parent=self.root,
            ):
                self.scan_status.set("Saved local servers retained. No model permissions changed.")
                return
            providers = detected
        try:
            self.apply_settings(
                self.settings.model_copy(update={"inference": True, "local_providers": providers})
            )
        except (OSError, ValueError):
            self.scan_status.set(
                "Local server settings were not saved. Check worker-folder access."
            )
            return
        self.scan_status.set(
            "Detected local text servers enabled. Current work finishes before inventory refreshes."
        )

    def finish_update(self) -> None:
        if self.controller and self.controller.running:
            self.root.after(100, self.finish_update)
            return
        if self.update_pending:
            from godfather_worker.updates import launch_update

            try:
                launch_update(*self.update_pending)
            except (OSError, ValueError):
                self.update_busy = False
                self.update_pending = None
                self.update_status.set("Update failed · Click to retry")
                return
            self.quit()

    def setup_local_ai(self) -> None:
        if self.local_setup_busy or self.update_busy:
            return
        if not self.identity:
            messagebox.showinfo(
                "Connect first", "Connect this computer to Command Center first.", parent=self.root
            )
            return
        if not messagebox.askyesno(
            "Set up local AI",
            "Download local model from Command Center? This enables local models and "
            "model downloads, and permits installation of verified Ollama files in your "
            "worker data folder. It uses this computer's storage and network. Current work "
            "finishes first; then choose your model in Command Center.",
            parent=self.root,
        ):
            return
        self.local_setup_pending = True
        self.local_setup_busy = True
        if self.controller and self.controller.running:
            self.controller.maintenance_event.set()
            self.status.set("Finishing current work before local AI setup…")
        else:
            self.begin_local_setup()

    def begin_local_setup(self) -> None:
        self.local_setup_pending = False
        self.status.set("Setting up Ollama. This download may take several minutes…")
        origin = (
            self.identity.get("origin", self.address.get()) if self.identity else self.address.get()
        )

        def setup() -> None:
            from godfather_worker.local_runtime import ensure_runtime

            try:
                asyncio.run(
                    ensure_runtime(
                        origin,
                        self.folder,
                        ProviderConfig(id="local-ollama", provider="ollama"),
                        True,
                    )
                )
                self.event("local_setup_ready")
            except (OSError, ValueError):
                self.event("local_setup_failed")

        self.background(setup)

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

    def set_connection_state(self, state: str) -> None:
        self.connection_state.set(state)
        self.connection_badge.configure(background="#176044" if state == "CONNECTED" else "#58431B")
        self.secure_label.pack_forget()
        if (
            state == "CONNECTED"
            and self.controller
            and self.controller.origin.startswith("https://")
        ):
            self.secure_label.pack(side="left", before=self.footer_status, padx=(0, 5))

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
        advertisement = discover(include_models=False)
        if not path.exists() and identity is None:
            settings = first_run_contribution(advertisement.resources)
        self.event(
            "loaded",
            identity=identity,
            settings=settings,
            advertisement=advertisement,
            models=[],
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
        self.connect_button.configure(text="Cancel", state="normal")
        self.address_entry.configure(state="disabled")
        self.code.set("Match this code in your browser: " + pairing.challenge[:12].upper())
        self.status.set("Approve this computer in your browser. Connecting automatically...")
        self.set_connection_state("AWAITING APPROVAL")
        self.notebook.select(0)  # type: ignore[no-untyped-call]
        self.show()
        # Paint the comparison code before the browser can cover the worker.
        self.root.update_idletasks()

        def exchange() -> None:
            try:
                identity = await_approval(pairing, self.store, self.cancel)
                if identity:
                    self.event("identity", identity=identity)
            except Exception as error:
                self.event(
                    "pairing_failed",
                    message=(
                        str(error) if isinstance(error, TimeoutError) else connection_error(error)
                    ),
                    code=pairing.challenge[:12].upper(),
                )
            finally:
                self.event("pairing_finished")

        self.background(exchange)
        webbrowser.open(pairing.browser_url)

    def resume(self) -> None:
        self.shared_inference.suspended = False
        self.start()
        self.shared_inference.refresh()

    def start(self) -> None:
        if not self.identity or self.closing or (self.controller and self.controller.running):
            return
        if self.shared_inference.activating or self.shared_inference.stopping:
            return
        try:
            self.settings = self.settings.model_copy(
                update={
                    "inference": self.inference.get(),
                    "model_installation": self.model_installation.get(),
                    "account_providers": self.account_connections.get(),
                }
            )
            self.controller = Controller(self.identity, self.folder, self.event)
            self.controller.start(
                self.settings, self.shared_inference.engine if self.shared_inference.ready else None
            )
            self.status.set("Connecting...")
            self.set_connection_state("CONNECTING")
            self.resume_button.configure(state="disabled")
            self.pause_button.configure(state="normal")
        except (ValueError, OSError) as error:
            messagebox.showerror("Worker settings", str(error))

    def apply_models(self) -> None:
        settings = self.settings.model_copy(
            update={
                "inference": self.inference.get(),
                "model_installation": self.model_installation.get(),
                "account_providers": self.account_connections.get(),
            }
        )
        try:
            if settings.model_installation and not settings.inference:
                raise ValueError("Enable local AI models before allowing model downloads.")
            if settings.runtime_installation and not settings.model_installation:
                raise ValueError("Enable model downloads before allowing Ollama runtime setup.")
            if settings.primary == "inference" and not settings.inference:
                raise ValueError(
                    "Choose CPU as the primary specialty before disabling local models."
                )
            self.apply_settings(settings)
        except (ValueError, OSError) as error:
            self.inference.set(self.settings.inference)
            self.model_installation.set(self.settings.model_installation)
            self.account_connections.set(self.settings.account_providers)
            messagebox.showerror("Model contribution", str(error), parent=self.root)

    def apply_settings(self, settings: Contribution, *, start: bool = False) -> None:
        """Re-register after the current attempt; changing sharing never needs a manual pause."""
        save_settings(self.folder / "settings.json", settings)
        self.settings = settings
        self.contribute.set(settings.share_with_workspaces)
        self.inference.set(settings.inference)
        self.model_installation.set(settings.model_installation)
        self.account_connections.set(settings.account_providers)
        self.shared.set(settings.shared)
        if self.controller and self.controller.running:
            self.settings_restart_pending = True
            self.controller.maintenance_event.set()
            self.status.set("Applying contribution settings automatically after current work...")
        elif start and self.identity:
            self.start()

    def apply_contribution(self) -> None:
        enabled = self.contribute.get()
        try:
            self.apply_settings(self.settings.with_workspace_contribution(enabled), start=enabled)
        except (ValueError, OSError) as error:
            self.contribute.set(self.settings.share_with_workspaces)
            messagebox.showerror("Computer contribution", str(error), parent=self.root)

    def restart_after_settings(self) -> None:
        if self.closing or not self.settings_restart_pending:
            return
        if self.controller and self.controller.running:
            self.root.after(100, self.restart_after_settings)
            return
        self.settings_restart_pending = False
        self.start()

    def pause(self) -> None:
        self.settings_restart_pending = False
        self.shared_inference.pending = None
        self.shared_inference.suspended = True
        self.shared_inference.stop_local(resume=False)
        if self.controller and self.controller.running:
            self.controller.stop()
            self.status.set("Pausing safely...")
            self.set_connection_state("PAUSING")

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
        if (
            self.pairing_busy
            or self.shared_inference.busy
            or self.shared_inference.engine
            or self.shared_inference.activating
            or self.shared_inference.stopping
            or (self.controller and self.controller.running)
        ):
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
            self.set_connection_state("DISCONNECTED")
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
        self.scan_cancel.set()
        self.shared_inference.cancel.set()
        self.show_update_progress(False)
        if self.update_timer:
            self.root.after_cancel(self.update_timer)
            self.update_timer = None
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
        if (
            self.pairing_busy
            or self.shared_inference.activating
            or self.shared_inference.stopping
            or self.shared_inference.busy
            or (self.controller and self.controller.running)
        ):
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
        if self.update_timer:
            self.root.after_cancel(self.update_timer)
        self.update_timer = self.root.after(1000, self.periodic_update_check)
        if not self.cancel.is_set():
            self.start()
        else:
            self.status.set("Connection saved. Paused.")
            self.set_connection_state("PAUSED")
            self.resume_button.configure(state="normal")

    def show_project_readiness(self, issues: list[dict[str, str]]) -> None:
        self.projects_checked = True
        repositories = {str(repository.id): repository for repository in self.settings.repositories}
        self.project_issues = {
            issue["repository_id"]: issue["code"]
            for issue in issues
            if issue.get("repository_id") in repositories and issue.get("code") in PROJECT_ISSUES
        }
        messages = [
            f"{repositories[identity].name}: {PROJECT_ISSUES[code][0]}"
            for identity, code in self.project_issues.items()
        ]
        if messages:
            others = (
                f" {len(messages) - 1} more project(s) need attention; select them in Projects."
                if len(messages) > 1
                else ""
            )
            self.project_warning.set(
                messages[0] + " Other enabled work can continue. "
                "Open Projects for repair steps." + others
            )
            self.project_notice.pack(fill="x", pady=(12, 0))
        else:
            self.project_warning.set("")
            self.project_notice.pack_forget()
        if self.project_editor:
            self.project_editor.refresh_projects()

    def pump(self) -> None:
        self.timer = None
        while not self.events.empty():
            name, values = self.events.get_nowait()
            if name == "network":
                self.network_checking = False
                self.network.set(values["message"])
            elif name == "scan_progress":
                self.scan_status.set(values["message"])
            elif name in ("scan_finished", "scan_failed"):
                self.scan_busy = False
                self.scan_button.configure(state="normal")
                self.model_scan_button.configure(state="normal")
                self.cancel_scan_button.configure(state="disabled")
                if name == "scan_failed":
                    self.scan_status.set("Scan failed. Check folder access and scan again.")
                else:
                    self.scan_result = values["result"]
                    self.scan_table.delete(*self.scan_table.get_children())
                    for model in self.scan_result.models:
                        self.scan_table.insert(
                            "",
                            "end",
                            values=(
                                model.name,
                                "Local server" if model.served else "Files · runtime unverified",
                                model.location,
                            ),
                        )
                    summary = f"Found {len(self.scan_result.models)} model(s); limit 128."
                    if self.scan_result.omitted:
                        summary += f" {self.scan_result.omitted} additional result(s) omitted."
                    if self.scan_result.incomplete:
                        summary += (
                            " Scan cancelled or search safety limit reached; "
                            "narrow the folders and retry."
                        )
                    if self.scan_result.unreadable:
                        summary += f" {self.scan_result.unreadable} unreadable item(s) skipped."
                    self.scan_status.set(summary)
                    self.use_scanned_button.configure(
                        state="normal"
                        if self.scan_result.providers and not self.scan_result.cancelled
                        else "disabled"
                    )
            elif name == "update_checked":
                self.update_checking = False
                self.show_update_progress(False)
                self.update_info = values["item"]
                self.update_status.set(
                    "Update Available" if self.update_info else "Worker is up to date"
                )
                if self.update_info:
                    self.check_updates()
                if self.update_timer:
                    self.root.after_cancel(self.update_timer)
                self.update_timer = self.root.after(1800000, self.periodic_update_check)
            elif name == "update_failed":
                self.show_update_progress(False)
                self.update_busy = self.update_checking = False
                self.update_info = None
                self.update_status.set("Update failed · Click to retry")
                if self.update_timer:
                    self.root.after_cancel(self.update_timer)
                self.update_timer = self.root.after(1800000, self.periodic_update_check)
            elif name == "update_downloaded":
                self.show_update_progress(False)
                self.update_pending = (values["path"], values["sha256"])
                self.update_status.set("Update ready · Waiting…")
                if self.controller and self.controller.running:
                    self.controller.maintenance_event.set()
                else:
                    self.finish_update()
            elif name == "local_setup_ready":
                self.local_setup_busy = False
                from godfather_worker.desktop import save_settings

                self.settings = self.settings.model_copy(
                    update={
                        "inference": True,
                        "model_installation": True,
                        "runtime_installation": True,
                    }
                )
                save_settings(self.folder / "settings.json", self.settings)
                self.inference.set(True)
                self.model_installation.set(True)
                self.inventory.set(
                    "Ollama is ready. Choose a local model in Command Center "
                    "→ Models → Add / use model."
                )
                self.start()
                origin = (
                    self.identity.get("origin", self.address.get())
                    if self.identity
                    else self.address.get()
                )
                webbrowser.open(origin + "/models")
            elif name == "local_setup_failed":
                self.local_setup_busy = False
                self.status.set(
                    "Ollama setup failed. Check network, free storage and the published "
                    "runtime catalog; click Get started to retry."
                )
            elif name == "loaded":
                self.models = values["models"]
                self.inventory.set(
                    "Select Scan for Local Models to search installed libraries and local servers."
                )
                self.settings = values["settings"]
                self.autostart.set(values["startup"])
                self.inference.set(self.settings.inference)
                self.model_installation.set(self.settings.model_installation)
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
                self.contribute.set(self.settings.share_with_workspaces)
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
            elif name == "pairing_failed":
                self.set_connection_state("DISCONNECTED")
                self.status.set(values["message"])
                self.code.set(
                    "Previous code: "
                    + values["code"]
                    + " (inactive). Close the approval page and click Connect to try again."
                )
            elif name == "pairing_finished":
                self.pairing_busy = False
                self.connect_button.configure(text="Connect")
                if not self.identity:
                    self.connect_button.configure(state="normal")
                    self.address_entry.configure(state="normal")
                    if self.cancel.is_set():
                        self.status.set("Connection cancelled. Ready to connect.")
                        self.set_connection_state("DISCONNECTED")
                        self.code.set("")
            elif name in ("worker.registered", "worker.heartbeat"):
                if "available_models" in values:
                    self.models = values["available_models"]
                self.set_connection_state(
                    "CONNECTED" if values.get("state", "online") != "disabled" else "DISABLED"
                )
                self.status.set(
                    (
                        (
                            "Connected - contributing to workspace jobs"
                            if self.models or self.settings.workloads
                            else "Connected - waiting for an AI model"
                        )
                        if self.settings.share_with_workspaces
                        else "Connected"
                    )
                    if values.get("state", "online") != "disabled"
                    else "Node disabled by administrator"
                )
            elif name == "worker.project_readiness":
                self.show_project_readiness(values["issues"])
            elif name == "worker.coordinator_unavailable":
                self.set_connection_state("DISCONNECTED · RETRYING")
                self.status.set("Connection lost. Reconnecting automatically...")
            elif name == "worker.session_busy":
                self.set_connection_state("WAITING FOR SESSION")
                self.status.set("Waiting for your previous worker session to end safely...")
            elif name == "worker.request_refused":
                self.set_connection_state("ACCESS REFUSED")
                self.status.set(
                    "Connection refused. Ask your administrator to check this node's permission."
                )
            elif name == "worker.attempt_started":
                self.status.set("Connected - working on an AI job")
            elif name == "worker.attempt_finished":
                self.status.set("Connected - ready for your next job")
            elif name == "worker.stopped":
                self.set_connection_state("PAUSED" if self.identity else "DISCONNECTED")
                self.resume_button.configure(state="normal" if self.identity else "disabled")
                self.pause_button.configure(state="disabled")
                if self.status.get().startswith("Pausing"):
                    self.status.set("Paused")
                if self.shared_inference.worker_stopped():
                    pass
                elif self.update_pending:
                    self.root.after(100, self.finish_update)
                elif self.local_setup_pending:
                    self.root.after(100, self.begin_local_setup)
                elif self.settings_restart_pending and not self.closing:
                    self.root.after(100, self.restart_after_settings)
            elif name == "error":
                self.status.set(values["message"])
            elif name == "shared_update" or name == "project_update" and not self.closing:
                values["apply"]()
            elif name in ("show", "open", "resume", "pause", "quit"):
                {
                    "show": self.show,
                    "open": self.open_center,
                    "resume": self.resume,
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
                self.set_connection_state("DISCONNECTED")
                self.status.set(
                    "Worker could not continue. Check settings or contact your administrator."
                )
            if self.tray:
                self.tray.title = "Consigliere — The Godfather AI: " + self.status.get()[:80]
        if not self.destroyed:
            self.timer = self.root.after(100, self.pump)

    def periodic_update_check(self) -> None:
        self.update_timer = None
        self.update_info = None
        self.check_updates()


def main() -> int:
    if "--install" in sys.argv:
        from godfather_worker.macos_setup import main as install_main

        return install_main()
    logging.disable(logging.CRITICAL)

    def self_test_stage(stage: str) -> None:
        report = os.getenv("GODFATHER_SELF_TEST_REPORT")
        if report and "--self-test" in sys.argv:
            Path(report).write_text(
                json.dumps({"stage": stage, "worker_version": worker_version()}), encoding="utf-8"
            )

    self_test_stage("before_tk")
    root = tk.Tk()
    if "--self-test" in sys.argv:
        self_test_stage("tk_ready")
        from godfather_worker.client import WorkerClient
        from godfather_worker.pairing import check_connection

        # Load bundled public roots in the frozen executable, even for offline smoke.
        WorkerClient(WEB_ORIGIN, "")
        self_test_stage("tls_ready")
        if origin := os.getenv("GODFATHER_SELF_TEST_ORIGIN"):
            self_test_stage("checking_fresh_pairing")
            check_connection(origin)
            self_test_stage("fresh_pairing_pending")
        # Frozen builds need this fixed source file to pass into a worker sandbox.
        from godfather_worker.workloads import program_source

        assert program_source().is_file()
        self_test_stage("source_ready")
        from godfather_worker.llama_runtime import catalog
        from godfather_worker.shared_engine_transport import hostname

        assert catalog()["version"] == "b11846"
        assert callable(hostname)
        self_test_stage("shared_engine_ready")
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
