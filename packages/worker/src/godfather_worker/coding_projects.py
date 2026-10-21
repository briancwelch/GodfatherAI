"""Owner-operated project setup in the existing tray application."""

import asyncio
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

from godfather_contracts.coding import CodingRepository, CodingSetupOptions

from godfather_worker.coding_setup import check_project, local_images, project_config, setup_options
from godfather_worker.desktop import save_settings
from godfather_worker.desktop_layout import content_frame

if TYPE_CHECKING:
    from godfather_worker.desktop_app import Application


class Projects:
    def __init__(self, app: "Application") -> None:
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("Coding projects")
        self.window.transient(app.root)
        self.options: CodingSetupOptions | None = None
        self.images: dict[str, str] = {}
        self.workspaces: dict[str, Any] = {}
        frame = content_frame(self.window, maximum_width=740)
        ttk.Label(frame, text="Coding projects", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Only you may use these projects. Pause the worker before saving changes.",
            wraplength=570,
        ).pack(anchor="w", pady=8)
        self.projects = tk.Listbox(frame, height=3, exportselection=False)
        self.projects.pack(fill="x")
        self.refresh_projects()
        ttk.Button(frame, text="Remove selected project", command=self.remove).pack(
            anchor="w", pady=6
        )
        ttk.Button(
            frame,
            text="Toggle applying reviewed changes for selected project",
            command=self.toggle_apply,
        ).pack(anchor="w", pady=6)
        self.name, self.folder = tk.StringVar(), tk.StringVar()
        self.workspace, self.image = tk.StringVar(), tk.StringVar()
        self.patterns, self.command = tk.StringVar(), tk.StringVar()
        self.allow_apply = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Allow me to apply reviewed changes from Command Center",
            variable=self.allow_apply,
        ).pack(anchor="w", pady=6)
        self.status = tk.StringVar(
            value="Loading your workspaces and installed test environments..."
        )
        for label, variable in (("Project name", self.name), ("Git project folder", self.folder)):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=variable, width=65).pack(fill="x", pady=(0, 5))
        ttk.Button(frame, text="Choose folder...", command=self.browse).pack(
            anchor="w", pady=(0, 8)
        )
        ttk.Label(frame, text="Workspace").pack(anchor="w")
        self.workspace_box = ttk.Combobox(frame, textvariable=self.workspace, state="readonly")
        self.workspace_box.pack(fill="x", pady=(0, 8))
        ttk.Label(frame, text="Installed test environment (Docker image)").pack(anchor="w")
        self.image_box = ttk.Combobox(frame, textvariable=self.image, state="readonly")
        self.image_box.pack(fill="x", pady=(0, 8))
        for label, variable in (
            (
                "Allowed committed files (comma-separated patterns, e.g. src/*.py, tests/*.py)",
                self.patterns,
            ),
            (
                "Test command inside that environment (e.g. python -m unittest discover -s tests)",
                self.command,
            ),
        ):
            ttk.Label(frame, text=label, wraplength=570).pack(anchor="w")
            ttk.Entry(frame, textvariable=variable).pack(fill="x", pady=(0, 8))
        ttk.Label(
            frame,
            text=(
                "Choose a focused set of files. The agent returns a patch; your original "
                "project stays unchanged. Tests run offline in a disposable Linux container. "
                "Tools and dependencies must already be installed in the selected image."
            ),
            wraplength=570,
        ).pack(anchor="w", pady=6)
        ttk.Label(frame, textvariable=self.status, wraplength=570).pack(anchor="w", pady=6)
        self.save_button = ttk.Button(
            frame, text="Check and save project", command=self.save, state="disabled"
        )
        self.save_button.pack(anchor="w")
        ttk.Button(frame, text="Close", command=self.window.destroy).pack(anchor="w", pady=8)
        self.work(self.load, self.loaded)

    def work(self, action: Callable[[], Any], apply: Callable[[Any], None]) -> None:
        def deliver(callback: Callable[[], Any]) -> None:
            def guarded() -> None:
                if self.window.winfo_exists():
                    callback()

            self.app.event("project_update", apply=guarded)

        def run() -> None:
            try:
                result = action()
                deliver(lambda: apply(result))
            except Exception as error:
                message = (
                    str(error)
                    if isinstance(error, (ValueError, FileNotFoundError))
                    else (
                        "Setup unavailable. Check that the coordinator is updated, "
                        "Git is installed and Docker is running locally."
                    )
                )
                deliver(lambda: self.status.set(message))
                deliver(
                    lambda: self.save_button.configure(
                        state="normal" if self.options and self.images else "disabled"
                    )
                )

        threading.Thread(target=run, daemon=True).start()

    def load(self) -> tuple[CodingSetupOptions, dict[str, str]]:
        assert self.app.identity is not None
        origin = self.app.controller.origin if self.app.controller else self.app.address.get()
        return setup_options(self.app.identity, origin), asyncio.run(local_images(self.app.folder))

    def loaded(self, result: tuple[CodingSetupOptions, dict[str, str]]) -> None:
        self.options, self.images = result
        self.workspaces = {f"{w.name} ({str(w.id)[:8]})": w.id for w in self.options.workspaces}
        self.workspace_box.configure(values=list(self.workspaces))
        self.image_box.configure(values=list(self.images))
        if self.workspaces:
            self.workspace_box.current(0)
        if self.images:
            self.image_box.current(0)
        self.status.set(
            "Choose the project, workspace and test environment, then save."
            if self.images and self.workspaces
            else (
                "You need an accessible workspace and an installed Linux Docker image. "
                "No tools or images are installed automatically."
            )
        )
        self.save_button.configure(
            state="normal" if self.images and self.workspaces else "disabled"
        )

    def browse(self) -> None:
        path = filedialog.askdirectory(parent=self.window, title="Choose your Git project")
        if path:
            from pathlib import Path

            self.folder.set(path)
            self.name.set(Path(path).name)

    def editable(self) -> bool:
        if self.app.controller and self.app.controller.running:
            messagebox.showinfo(
                "Pause first",
                "Pause the worker, then save project changes. Resume afterward to publish them.",
                parent=self.window,
            )
            return False
        return True

    def refresh_projects(self) -> None:
        self.projects.delete(0, tk.END)
        for repo in self.app.settings.repositories:
            self.projects.insert(
                tk.END, repo.name + (" — Apply enabled" if repo.allow_apply else " — Preview only")
            )

    def toggle_apply(self) -> None:
        selected = self.projects.curselection()  # type: ignore[no-untyped-call]
        if selected and self.editable():
            repositories = list(self.app.settings.repositories)
            repo = repositories[selected[0]]
            repositories[selected[0]] = repo.model_copy(
                update={"allow_apply": not repo.allow_apply}
            )
            self.persist(repositories)

    def persist(self, repositories: list[CodingRepository]) -> None:
        if not self.editable():
            return
        settings = self.app.settings.model_copy(update={"repositories": repositories})
        save_settings(self.app.folder / "settings.json", settings)
        self.app.settings = settings
        self.refresh_projects()
        self.status.set(
            "Saved. Resume the worker, then refresh the repository list in Command Center."
        )

    def remove(self) -> None:
        selected = self.projects.curselection()  # type: ignore[no-untyped-call]
        if selected and self.editable():
            repositories = list(self.app.settings.repositories)
            repositories.pop(selected[0])
            self.persist(repositories)

    def save(self) -> None:
        if not self.editable() or self.options is None:
            return
        try:
            if len(self.app.settings.repositories) >= 8:
                raise ValueError(
                    "Up to eight projects are supported. Remove one before adding another."
                )
            repository = project_config(
                name=self.name.get(),
                path=self.folder.get(),
                image=self.images[self.image.get()],
                owner=self.options.owner_id,
                workspace=self.workspaces[self.workspace.get()],
                patterns=self.patterns.get(),
                test_command=self.command.get(),
            )
            repository = repository.model_copy(update={"allow_apply": self.allow_apply.get()})
            if any(r.path == repository.path for r in self.app.settings.repositories):
                raise ValueError(
                    "That project is already configured. Remove it before changing its scope."
                )
            self.save_button.configure(state="disabled")
            self.status.set("Checking Git and your selected local environment...")

            def check() -> CodingRepository:
                asyncio.run(check_project(repository))
                return repository

            def saved(repo: CodingRepository) -> None:
                self.persist([*self.app.settings.repositories, repo])
                self.save_button.configure(state="normal")

            self.work(check, saved)
        except (ValueError, OSError, KeyError) as error:
            self.status.set(
                str(error)
                if isinstance(error, ValueError)
                else "Choose a valid folder, workspace and environment."
            )
