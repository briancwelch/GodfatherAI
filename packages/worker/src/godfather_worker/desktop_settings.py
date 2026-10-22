"""Tabbed, owner-controlled settings; presentation does not require pausing work."""

import asyncio
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from godfather_worker import desktop_theme
from godfather_worker.coding_setup import local_images
from godfather_worker.desktop import Contribution, save_settings
from godfather_worker.desktop_layout import window_size
from godfather_worker.native_desktop import set_login_startup

if TYPE_CHECKING:
    from godfather_worker.desktop_app import Application


class Settings:
    def __init__(self, app: "Application") -> None:
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("Consigliere — Settings")
        self.window.transient(app.root)
        window_size(self.window, 940, 650)
        self.values: dict[str, tk.StringVar | tk.BooleanVar] = {}
        self.images: dict[str, str] = {}
        self.status = tk.StringVar(
            value="Changes to contributions require Pause. Appearance can change while working."
        )
        header = ttk.Frame(self.window, padding=(20, 16))
        header.pack(fill="x")
        ttk.Label(header, text="Settings", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=app.hardware, style="Muted.TLabel").pack(side="right")
        footer = ttk.Frame(self.window, padding=(20, 12))
        footer.pack(side="bottom", fill="x")
        ttk.Label(footer, textvariable=self.status, wraplength=570, style="Muted.TLabel").pack(
            side="left"
        )
        ttk.Button(footer, text="Cancel", command=self.window.destroy).pack(side="right")
        ttk.Button(footer, text="Save settings", command=self.save).pack(side="right", padx=8)
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self.pages: dict[str, ttk.Frame] = {}
        for name in ("General", "Resources", "Workloads", "Sharing", "Appearance", "Connection"):
            page = ttk.Frame(self.notebook, padding=18)
            self.notebook.add(page, text=name)
            self.pages[name] = page
        preferences = app.preferences
        self.check(
            "General",
            "Install verified worker updates automatically when idle (without prompting)",
            "automatic_updates",
            preferences.automatic_updates,
        )
        self.check("General", "Start Consigliere when I sign in", "startup", app.autostart.get())
        self.check(
            "General",
            "Start with the window minimized to the tray",
            "start_minimized",
            preferences.start_minimized,
        )
        self.check(
            "General",
            "Keep working in the tray when I close the window",
            "close_to_tray",
            preferences.close_to_tray,
        )
        self.note(
            "General",
            (
                "Use File → Quit to stop the app. If the tray is unavailable, clo"
                "sing the window exits safely. Startup changes affect only your O"
                "S account."
            ),
        )
        self.entry(
            "Resources", "CPU scheduling cores", "cpu", str(app.settings.cpu_cores), spinner=True
        )
        self.entry(
            "Resources",
            "RAM scheduling allowance (GiB)",
            "ram",
            str(app.settings.ram_gib),
            spinner=True,
        )
        self.choice(
            "Resources", "Primary specialty", "primary", app.settings.primary, ["cpu", "inference"]
        )
        self.check(
            "Resources", "Allow my existing local AI models", "inference", app.settings.inference
        )
        self.check(
            "Resources",
            "Allow model downloads from Command Center",
            "model_installation",
            app.settings.model_installation,
        )
        self.check(
            "Resources",
            "Allow Command Center to install local Ollama on this computer",
            "runtime_installation",
            app.settings.runtime_installation,
        )
        self.note(
            "Resources",
            "Model downloads require local AI models enabled. Runtime setup can install "
            "or start Ollama when separately enabled above. "
            "Each download requires confirmation in Command Center and uses this "
            "computer's network and storage.",
        )
        self.check(
            "Resources",
            "Use API connections authorized for this computer",
            "account_providers",
            app.settings.account_providers,
        )
        self.note(
            "Resources",
            (
                "These are scheduler allowances. Local inference is not an OS res"
                "ource cap. Each data stage is isolated to one CPU and 512 MiB; c"
                "oding retains its existing sandbox."
            ),
        )
        workloads = app.settings.workloads
        self.check(
            "Workloads",
            "Allow analytics and report processing",
            "data_enabled",
            bool(workloads and workloads.image),
        )
        self.data_box = self.entry(
            "Workloads",
            "Existing Python environment (installed Docker image or pinned digest)",
            "data_image",
            workloads.image or "" if workloads else "",
            combo=True,
        )
        self.check(
            "Workloads",
            "Allow image generation through my installed local backend",
            "images_enabled",
            bool(workloads and workloads.images),
        )
        self.entry(
            "Workloads",
            "Local image API address",
            "image_url",
            workloads.images.url if workloads and workloads.images else "http://127.0.0.1:7860",
        )
        self.entry(
            "Workloads",
            "Permitted installed model names (comma separated)",
            "image_models",
            ",".join(workloads.images.models) if workloads and workloads.images else "",
        )
        self.note(
            "Workloads",
            (
                "Nothing is downloaded or installed. An unavailable environment i"
                "s not advertised. Image connections are local only; no cloud fal"
                "lback is permitted."
            ),
        )
        self.check("Sharing", "Accept explicitly shared work", "shared", app.settings.shared)
        self.entry(
            "Sharing",
            "Allowed job owner IDs (comma separated)",
            "owners",
            ",".join(map(str, app.settings.allowed_owner_ids)),
        )
        self.entry(
            "Sharing",
            "Allowed workspace IDs (comma separated)",
            "workspaces",
            ",".join(map(str, app.settings.allowed_workspace_ids)),
        )
        self.note(
            "Sharing",
            (
                "Private by default. Shared work needs both owner and workspace g"
                "rants. Platform administrators cannot bypass these local restric"
                "tions. Project access remains separately controlled in Projects."
            ),
        )
        self.choice("Appearance", "Theme", "theme", preferences.theme, ["light", "dark"])
        self.choice(
            "Appearance",
            "Text size",
            "font_size",
            str(preferences.font_size),
            ["9", "10", "11", "12", "14"],
        )
        self.check(
            "Appearance", "Remember the window size", "remember_size", preferences.remember_size
        )
        ttk.Button(
            self.pages["Appearance"],
            text="Reset main window size",
            command=lambda: window_size(app.root),
        ).pack(anchor="w", pady=12)
        self.note(
            "Appearance",
            (
                "The window expands to use available space. Only project tables w"
                "ith overflowing rows show a scrollbar. Appearance preferences ar"
                "e stored locally and never shared with another owner."
            ),
        )
        ttk.Label(self.pages["Connection"], textvariable=app.owner, style="Title.TLabel").pack(
            anchor="w", pady=(0, 12)
        )
        ttk.Label(self.pages["Connection"], textvariable=app.address, wraplength=650).pack(
            anchor="w"
        )
        ttk.Label(self.pages["Connection"], textvariable=app.network, wraplength=650).pack(
            anchor="w", pady=16
        )
        ttk.Button(
            self.pages["Connection"], text="Refresh network status", command=app.refresh_network
        ).pack(anchor="w", pady=4)
        ttk.Button(
            self.pages["Connection"], text="Open Command Center", command=app.open_center
        ).pack(anchor="w", pady=4)
        ttk.Button(
            self.pages["Connection"], text="Disconnect this computer…", command=app.forget
        ).pack(anchor="w", pady=16)
        self.note(
            "Connection",
            (
                "Disconnect removes this computer's local connection only. Revoke"
                " the machine credential in Command Center to end remote authoriz"
                "ation. No DNS or network configuration is changed here."
            ),
        )
        self.refresh_images()

    def note(self, page: str, text: str) -> None:
        ttk.Label(self.pages[page], text=text, wraplength=760, style="Muted.TLabel").pack(
            anchor="w", pady=(12, 0)
        )

    def check(self, page: str, label: str, key: str, value: bool) -> None:
        variable = tk.BooleanVar(self.window, value=value)
        self.values[key] = variable
        ttk.Checkbutton(self.pages[page], text=label, variable=variable).pack(anchor="w", pady=4)

    def entry(
        self,
        page: str,
        label: str,
        key: str,
        value: str,
        *,
        spinner: bool = False,
        combo: bool = False,
    ) -> ttk.Entry | ttk.Combobox | ttk.Spinbox:
        ttk.Label(self.pages[page], text=label).pack(anchor="w", pady=(8, 3))
        variable = tk.StringVar(self.window, value=value)
        self.values[key] = variable
        widget: ttk.Entry | ttk.Combobox | ttk.Spinbox
        if spinner:
            widget = ttk.Spinbox(
                self.pages[page], textvariable=variable, from_=1, to=65536, width=12
            )
        elif combo:
            widget = ttk.Combobox(self.pages[page], textvariable=variable)
        else:
            widget = ttk.Entry(self.pages[page], textvariable=variable)
        widget.pack(fill="x", pady=(0, 5))
        return widget

    def choice(self, page: str, label: str, key: str, value: str, choices: list[str]) -> None:
        widget = self.entry(page, label, key, value, combo=True)
        assert isinstance(widget, ttk.Combobox)
        widget.configure(state="readonly", values=choices)

    def refresh_images(self) -> None:
        def found() -> None:
            try:
                images = asyncio.run(local_images(self.app.folder))
            except (ValueError, OSError):
                return

            def update() -> None:
                if self.window.winfo_exists():
                    self.images = images
                    assert isinstance(self.data_box, ttk.Combobox)
                    self.data_box.configure(values=list(images))
                    selected = str(self.values["data_image"].get())
                    match = next(
                        (name for name, digest in images.items() if digest == selected), None
                    )
                    if match:
                        variable = self.values["data_image"]
                        assert isinstance(variable, tk.StringVar)
                        variable.set(match)

            self.app.event("project_update", apply=update)

        self.app.background(found)

    def save(self) -> None:
        from godfather_worker.workloads import WorkloadConfig

        values = {key: variable.get() for key, variable in self.values.items()}
        try:
            workloads = None
            if values["data_enabled"] or values["images_enabled"]:
                workloads = WorkloadConfig.model_validate(
                    {
                        "image": self.images.get(
                            str(values["data_image"]), str(values["data_image"])
                        )
                        if values["data_enabled"]
                        else None,
                        "images": {
                            "url": values["image_url"],
                            "models": [
                                m.strip()
                                for m in str(values["image_models"]).split(",")
                                if m.strip()
                            ],
                        }
                        if values["images_enabled"]
                        else None,
                    }
                )
            settings = Contribution.model_validate(
                {
                    **self.app.settings.model_dump(),
                    "workloads": workloads,
                    "cpu_cores": int(values["cpu"]),
                    "ram_gib": int(values["ram"]),
                    "primary": values["primary"],
                    "inference": values["inference"],
                    "model_installation": values["model_installation"],
                    "runtime_installation": values["runtime_installation"],
                    "account_providers": values["account_providers"],
                    "shared": values["shared"],
                    "allowed_owner_ids": [
                        s.strip() for s in str(values["owners"]).split(",") if s.strip()
                    ],
                    "allowed_workspace_ids": [
                        s.strip() for s in str(values["workspaces"]).split(",") if s.strip()
                    ],
                }
            )
            if settings.shared and not (
                settings.allowed_owner_ids and settings.allowed_workspace_ids
            ):
                raise ValueError("Shared work needs explicit owner and workspace grants.")
            if settings.primary == "inference" and not settings.inference:
                raise ValueError("Enable local models before choosing inference as primary.")
            if settings.model_installation and not settings.inference:
                self.status.set("Enable local AI models before allowing model downloads.")
                return
            if settings.runtime_installation and not settings.model_installation:
                self.status.set("Enable model downloads before approving Ollama runtime setup.")
                return
            if (
                settings != self.app.settings
                and self.app.controller
                and self.app.controller.running
            ):
                self.status.set(
                    "Pause the worker before changing contributions. Appearance-only "
                    "changes can be saved now."
                )
                return
            preferences = desktop_theme.Preferences.model_validate(
                {
                    **self.app.preferences.model_dump(),
                    **{
                        key: values[key]
                        for key in (
                            "theme",
                            "font_size",
                            "close_to_tray",
                            "start_minimized",
                            "remember_size",
                            "automatic_updates",
                        )
                    },
                    "width": max(640, self.app.root.winfo_width()),
                    "height": max(480, self.app.root.winfo_height()),
                }
            )
            if bool(values["startup"]) != self.app.autostart.get():
                set_login_startup(bool(values["startup"]))
            save_settings(self.app.folder / "settings.json", settings)
            desktop_theme.save(self.app.folder, preferences)
            self.app.settings, self.app.preferences = settings, preferences
            self.app.inference.set(settings.inference)
            self.app.model_installation.set(settings.model_installation)
            self.app.account_connections.set(settings.account_providers)
            self.app.autostart.set(bool(values["startup"]))
            self.app.cpu.set(str(settings.cpu_cores))
            self.app.ram.set(str(settings.ram_gib))
            self.app.shared.set(settings.shared)
            colors = desktop_theme.apply(ttk.Style(self.app.root), preferences)
            self.app.root.configure(background=colors["workspace"])
            self.window.destroy()
        except (ValueError, OSError):
            self.status.set(
                "Settings were not fully saved. Check capacity, UUID grants and "
                "installed environment/model values. Image APIs must use loopback HTTP."
            )
