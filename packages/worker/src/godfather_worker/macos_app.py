"""Small macOS desktop application using bundled Python/Tk and native Keychain."""

import asyncio
import json
import logging
import platform
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
    login_startup,
    open_tailscale_setup,
)
from godfather_worker.discovery import discover
from godfather_worker.inference import discover_models
from godfather_worker.keychain import Keychain


class Application:
    def __init__(self, root: tk.Tk, folder: Path) -> None:
        self.root, self.folder = root, folder
        self.store = Keychain()
        self.identity: dict[str, str] | None = None
        self.controller: Controller | None = None
        self.pairing: Pairing | None = None
        self.events: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self.settings = Contribution()
        self.closing = False
        self.pairing_busy = False
        self.forgotten = False
        self.models: list[str] = []
        self.job = "Idle"
        self.status = tk.StringVar(value="Loading local identity and hardware…")
        self.owner = tk.StringVar(value="Not signed in")
        self.node = tk.StringVar(value="Not enrolled")
        self.hardware = tk.StringVar(value="Detecting hardware…")
        self.inventory = tk.StringVar(value="Checking existing local models…")
        self.job_status = tk.StringVar(value="Idle")
        self.code = tk.StringVar(value="")
        self.cpu = tk.StringVar(value="1")
        self.ram = tk.StringVar(value="2")
        self.inference = tk.BooleanVar(value=False)
        self.primary = tk.StringVar(value="cpu")
        self.shared = tk.BooleanVar(value=False)
        self.owners = tk.StringVar(value="")
        self.workspaces = tk.StringVar(value="")
        self.autostart = tk.BooleanVar(value=False)
        root.title("The Godfather Worker")
        root.minsize(640, 680)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="The Godfather Worker", font=("Helvetica", 22, "bold")).pack(
            anchor="w"
        )
        for variable in (self.status, self.node, self.owner, self.hardware, self.inventory):
            ttk.Label(frame, textvariable=variable, wraplength=590).pack(anchor="w", pady=5)
        connect = ttk.Frame(frame)
        connect.pack(fill="x", pady=8)
        self.connect_button = ttk.Button(
            connect, text="Connect to The Godfather", command=self.connect
        )
        self.connect_button.pack(side="left")
        self.finish_button = ttk.Button(
            connect, text="Finish connecting", command=self.finish, state="disabled"
        )
        self.finish_button.pack(side="left", padx=8)
        ttk.Label(frame, textvariable=self.code).pack(anchor="w")
        ttk.Button(frame, text="Set up Tailscale", command=open_tailscale_setup).pack(
            anchor="w", pady=5
        )
        ttk.Separator(frame).pack(fill="x", pady=10)
        ttk.Label(frame, text="Contribution settings", font=("Helvetica", 14, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            frame,
            text="Available: CPU availability and optional local inference\n"
            "Maximum concurrent jobs: 1 (current runtime limit)",
            wraplength=590,
        ).pack(anchor="w", pady=5)
        ttk.Label(frame, text="Primary capability (the other is secondary if enabled)").pack(
            anchor="w"
        )
        ttk.Combobox(
            frame,
            textvariable=self.primary,
            values=("cpu", "inference"),
            state="readonly",
            width=18,
        ).pack(anchor="w", pady=4)
        budgets = ttk.Frame(frame)
        budgets.pack(fill="x")
        ttk.Label(budgets, text="CPU scheduling cores").pack(side="left")
        ttk.Spinbox(budgets, from_=1, to=128, textvariable=self.cpu, width=5).pack(
            side="left", padx=8
        )
        ttk.Label(budgets, text="RAM scheduling GiB").pack(side="left")
        ttk.Spinbox(budgets, from_=1, to=1024, textvariable=self.ram, width=5).pack(
            side="left", padx=8
        )
        ttk.Label(
            frame,
            text="Budgets limit advertised scheduling capacity, not actual OS or Ollama usage. "
            "CPU-only mode connects without executing tools or jobs. No files or shell exposed.",
            wraplength=590,
        ).pack(anchor="w", pady=6)
        ttk.Checkbutton(
            frame, text="Use existing local Ollama models (no downloads)", variable=self.inference
        ).pack(anchor="w")
        ttk.Checkbutton(
            frame, text="Accept shared workloads only from these IDs", variable=self.shared
        ).pack(anchor="w")
        for label, variable in (
            ("Allowed owner IDs (comma separated)", self.owners),
            ("Allowed workspace IDs (comma separated)", self.workspaces),
        ):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=variable).pack(fill="x")
        ttk.Checkbutton(
            frame,
            text="Start the app and worker at login using saved settings",
            variable=self.autostart,
            command=self.set_startup,
        ).pack(anchor="w", pady=5)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=12)
        self.start_button = ttk.Button(
            actions, text="Start Worker", command=self.start, state="disabled"
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            actions, text="Stop / Pause Worker", command=self.stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Diagnostics", command=self.diagnostics).pack(side="left")
        ttk.Label(frame, textvariable=self.job_status).pack(anchor="w")
        ttk.Button(frame, text="Forget this Mac locally…", command=self.forget).pack(
            anchor="w", pady=8
        )
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.background(self.load)
        root.after(100, self.pump)

    def event(self, name: str, **values: Any) -> None:
        self.events.put((name, values))

    def background(self, action: Callable[[], None]) -> None:
        def work() -> None:
            try:
                action()
            except Exception as error:
                self.event("error", message=connection_error(error))

        threading.Thread(target=work, daemon=True).start()

    def load(self) -> None:
        saved = self.store.read()
        identity = json.loads(saved) if saved else None
        settings_path = self.folder / "settings.json"
        settings = (
            Contribution.model_validate_json(settings_path.read_text())
            if settings_path.exists()
            else Contribution()
        )
        advertisement = discover()
        deployments = asyncio.run(
            discover_models([ProviderConfig(id="local-ollama", provider="ollama")])
        )
        self.event(
            "loaded",
            identity=identity,
            settings=settings,
            advertisement=advertisement,
            models=[m.identifier for m in deployments],
        )

    def connect(self) -> None:
        if self.identity or self.pairing_busy:
            return
        self.pairing = Pairing()
        self.code.set("Match this browser code: " + self.pairing.challenge[:12].upper())
        self.status.set("Sign in with Google, approve this Mac, then click Finish connecting.")
        self.finish_button.configure(state="normal")
        webbrowser.open(self.pairing.browser_url)

    def finish(self) -> None:
        if not self.pairing or self.pairing_busy:
            return
        self.pairing_busy = True
        self.finish_button.configure(state="disabled")
        self.status.set("Finishing secure connection…")

        def exchange() -> None:
            assert self.pairing is not None
            try:
                identity = self.pairing.exchange(self.store)
                self.event("identity", identity=identity)
            finally:
                self.event("pairing_finished")

        self.background(exchange)

    def start(self) -> None:
        if not self.identity:
            return
        try:
            self.settings = Contribution.model_validate(
                {
                    "cpu_cores": int(self.cpu.get()),
                    "ram_gib": int(self.ram.get()),
                    "inference": self.inference.get(),
                    "primary": self.primary.get(),
                    "shared": self.shared.get(),
                    "allowed_owner_ids": [
                        s.strip() for s in self.owners.get().split(",") if s.strip()
                    ],
                    "allowed_workspace_ids": [
                        s.strip() for s in self.workspaces.get().split(",") if s.strip()
                    ],
                }
            )
            if self.settings.inference and not self.models:
                raise ValueError(
                    "No local Ollama models found. Start your runtime and restart the app, "
                    "or turn off inference."
                )
            self.controller = Controller(self.identity, self.folder, self.event)
            self.controller.start(self.settings)
            self.status.set("Connecting to the private coordinator…")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        except (ValueError, OSError):
            messagebox.showerror(
                "Check contribution settings",
                "Use valid CPU/RAM budgets and explicit UUID lists for sharing. "
                "Inference needs existing models in a running local Ollama runtime.",
            )

    def stop(self) -> None:
        if self.controller:
            self.controller.stop()
            self.status.set("Stopping; waiting for the current request to close…")

    @property
    def agent(self) -> Path:
        return Path.home() / "Library/LaunchAgents/ai.the-godfather.worker.plist"

    def set_startup(self) -> None:
        try:
            login_startup(self.autostart.get(), Path(sys.executable), self.agent)
        except (ValueError, OSError):
            self.autostart.set(False)
            messagebox.showerror(
                "Login startup",
                "Install the app in Applications first. Login startup could not be saved.",
            )

    def forget(self) -> None:
        if self.controller and self.controller.running:
            messagebox.showinfo(
                "Stop worker first", "Stop the worker and wait before forgetting this Mac."
            )
            return
        if messagebox.askyesno(
            "Forget this Mac",
            "First revoke this Mac in Command Center → Administration → Owned node onboarding. "
            "Remove this app's local identity and saved contribution settings now?",
        ):
            try:
                self.store.delete()
                login_startup(False, Path(sys.executable), self.agent)
                for name in ("settings.json", "settings.tmp", "ollama.json"):
                    (self.folder / name).unlink(missing_ok=True)
                self.identity = None
                self.forgotten = True
                self.node.set("Not enrolled")
                self.owner.set("Not signed in")
                self.status.set(
                    "Local identity removed. Remote revocation must be completed in Command Center."
                )
                self.start_button.configure(state="disabled")
                self.connect_button.configure(state="normal")
            except OSError:
                messagebox.showerror(
                    "Removal incomplete",
                    "Unlock Keychain and check the worker's local folder permissions.",
                )

    def diagnostics(self) -> None:
        messagebox.showinfo(
            "Diagnostics",
            f"{self.status.get()}\n{self.hardware.get()}\n{self.inventory.get()}\n"
            "Private Tailscale access and private API DNS are required. "
            "Ask your administrator to check TCP 443 grants. "
            "No model or runtime is installed automatically.\n" + WEB_ORIGIN,
        )

    def close(self) -> None:
        self.closing = True
        self.stop()
        self.await_close()

    def await_close(self) -> None:
        if self.pairing_busy or (self.controller and self.controller.running):
            self.root.after(100, self.await_close)
        else:
            self.root.destroy()

    def pump(self) -> None:
        while not self.events.empty():
            name, values = self.events.get_nowait()
            if name == "loaded":
                advertisement = values["advertisement"]
                self.models = values["models"]
                resources = advertisement.resources
                ram = (
                    f"{resources.ram_bytes / 1024**3:.1f} GiB RAM"
                    if resources.ram_bytes
                    else "RAM unknown"
                )
                gpu = (
                    ", ".join(f"{g.name} ({g.backend}, reported)" for g in resources.gpus)
                    or "CPU only / GPU unavailable"
                )
                self.hardware.set(
                    f"{advertisement.architecture} · {resources.cpu_count} cores · {ram}\n{gpu}"
                )
                self.inventory.set(
                    "Local models: "
                    + (
                        ", ".join(self.models)
                        or "None. CPU-only connection available; inference needs a local runtime."
                    )
                )
                self.settings = values["settings"]
                self.cpu.set(str(self.settings.cpu_cores))
                self.ram.set(str(self.settings.ram_gib))
                self.inference.set(self.settings.inference)
                self.primary.set(self.settings.primary)
                self.shared.set(self.settings.shared)
                self.owners.set(",".join(map(str, self.settings.allowed_owner_ids)))
                self.workspaces.set(",".join(map(str, self.settings.allowed_workspace_ids)))
                self.autostart.set(self.agent.exists())
                if values["identity"]:
                    self.show_identity(values["identity"])
                    if "--login" in sys.argv and self.autostart.get():
                        self.start()
                else:
                    self.status.set("Ready to connect")
            elif name == "identity":
                self.show_identity(values["identity"])
            elif name == "pairing_finished":
                self.pairing_busy = False
                # A network loss may have consumed the grant. Never silently replay it.
                self.pairing = None
                self.finish_button.configure(state="disabled")
            elif name in ("worker.registered", "worker.heartbeat"):
                self.status.set(
                    "Connected" if values.get("state", "online") != "disabled" else "Node disabled"
                )
            elif name == "worker.attempt_started":
                self.job = "Running job " + str(values["job_id"])
                self.job_status.set(self.job)
            elif name == "worker.attempt_finished":
                self.job_status.set("Idle — last attempt ended; result is in Command Center")
            elif name == "worker.coordinator_unavailable":
                self.status.set("Disconnected — retrying. Check Tailscale and private DNS.")
            elif name == "worker.session_busy":
                self.status.set("Waiting for the previous worker session to expire safely…")
            elif name == "worker.request_refused":
                self.status.set(
                    "Access refused — revoked credential, disabled node, or missing permission. "
                    "Contact your administrator."
                )
            elif name == "worker.stopped":
                self.stop_button.configure(state="disabled")
                if self.identity:
                    self.start_button.configure(state="normal")
                self.job_status.set(
                    "Worker stopped; interrupted attempts use existing lease recovery"
                )
                if self.status.get().startswith("Stopping"):
                    self.status.set("Stopped / paused")
            elif name == "error":
                self.status.set(values["message"])
            elif name in (
                "worker.unexpected_error",
                "worker.configuration_invalid",
                "worker.invalid_coordinator_response",
            ):
                self.status.set(
                    "Worker could not continue. Check diagnostics and contact your administrator."
                )
        self.root.after(100, self.pump)

    def show_identity(self, identity: dict[str, str]) -> None:
        self.identity = identity
        self.forgotten = False
        self.node.set("Node: " + identity.get("name", "Mac"))
        self.owner.set("Owner: " + identity.get("owner", "Unknown"))
        self.status.set("Enrolled — choose contributions and click Start Worker")
        self.start_button.configure(state="normal")
        self.connect_button.configure(state="disabled")
        self.finish_button.configure(state="disabled")
        self.code.set("")


def main() -> int:
    if "--self-test" in sys.argv:
        if platform.system() != "Darwin":
            raise RuntimeError("Native macOS build required")
        root = tk.Tk()
        root.withdraw()
        root.update()
        root.destroy()
        Keychain()  # Load native frameworks, without reading or writing credentials.
        return 0
    if platform.system() != "Darwin":
        raise RuntimeError("This application requires macOS")
    import importlib

    fcntl = importlib.import_module("fcntl")

    logging.disable(logging.CRITICAL)  # No library/provider response bodies in GUI logs.
    folder = Path.home() / "Library/Application Support/The Godfather Worker"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / "app.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        root = tk.Tk()
        application = Application(root, folder)
        root.mainloop()
    if application.forgotten:
        (folder / "app.lock").unlink(missing_ok=True)
        with suppress(OSError):
            folder.rmdir()  # Only if empty; never remove other files recursively.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
