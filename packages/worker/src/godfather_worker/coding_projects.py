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
from godfather_worker.desktop_layout import table_scroll
from godfather_worker.project_readiness import PROJECT_ISSUES, project_issue_message

if TYPE_CHECKING:
    from godfather_worker.desktop_app import Application


class Projects:
    def __init__(self, app: "Application", parent: ttk.Frame) -> None:
        self.app = app
        self.window = parent
        self.options: CodingSetupOptions | None = None
        self.images: dict[str, str] = {}
        self.workspaces: dict[str, Any] = {}
        frame = ttk.Frame(parent, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Coding projects", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "Private project grants · Pause before changing access · "
                "Review patches before applying"
            ),
            style="Muted.TLabel",
            wraplength=650,
        ).pack(anchor="w", pady=(4, 12))
        panes = ttk.Panedwindow(frame, orient="horizontal")
        panes.pack(fill="both", expand=True)
        library = ttk.Frame(panes, padding=(0, 0, 16, 0))
        editor = ttk.Frame(panes)
        panes.add(library, weight=2)
        panes.add(editor, weight=3)
        ttk.Label(library, text="APPROVED PROJECTS", style="Muted.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        rows = ttk.Frame(library)
        rows.pack(fill="both", expand=True)
        rows.rowconfigure(0, weight=1)
        rows.columnconfigure(0, weight=1)
        self.projects = ttk.Treeview(
            rows,
            columns=("project", "readiness", "apply"),
            show="headings",
            selectmode="browse",
            height=6,
        )
        self.projects.heading("project", text="Project")
        self.projects.heading("apply", text="Changes")
        self.projects.heading("readiness", text="Availability")
        self.projects.column("project", width=140, minwidth=80)
        self.projects.column("readiness", width=110, minwidth=90)
        self.projects.column("apply", width=100, minwidth=80, stretch=False)
        self.projects.grid(row=0, column=0, sticky="nsew")
        table_scroll(rows, self.projects)
        self.readiness = tk.StringVar(value="Resume checks saved project dependencies.")
        self.projects.bind("<<TreeviewSelect>>", self.selected_readiness)
        self.refresh_projects()
        controls = ttk.Frame(library)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Remove", command=self.remove).pack(side="left")
        ttk.Button(controls, text="Allow / disable Apply", command=self.toggle_apply).pack(
            side="left", padx=6
        )
        ttk.Label(library, textvariable=self.readiness, wraplength=300).pack(
            anchor="w", fill="x", pady=(10, 0)
        )
        self.name, self.folder = tk.StringVar(), tk.StringVar()
        self.workspace, self.image = tk.StringVar(), tk.StringVar()
        self.patterns, self.command = tk.StringVar(), tk.StringVar()
        self.allow_apply = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Loading your workspaces and installed test environments…")
        ttk.Label(editor, text="ADD PROJECT", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        tabs = ttk.Notebook(editor)
        tabs.pack(fill="both", expand=True)
        details = ttk.Frame(tabs, padding=12)
        scope = ttk.Frame(tabs, padding=12)
        tabs.add(details, text="Project details")
        tabs.add(scope, text="Files & testing")
        details.columnconfigure(0, weight=1)
        details.columnconfigure(1, weight=1)
        for index, (label, variable) in enumerate(
            (("Project name", self.name), ("Git project folder", self.folder))
        ):
            cell = ttk.Frame(details, padding=(0, 0, 8 if index == 0 else 0, 0))
            cell.grid(row=0, column=index, sticky="ew")
            ttk.Label(cell, text=label).pack(anchor="w")
            row = ttk.Frame(cell)
            row.pack(fill="x", pady=(3, 10))
            ttk.Entry(row, textvariable=variable, width=12).pack(side="left", fill="x", expand=True)
            if variable is self.folder:
                ttk.Button(row, text="Browse…", command=self.browse).pack(side="right", padx=(6, 0))
        workspace_cell = ttk.Frame(details, padding=(0, 0, 8, 0))
        workspace_cell.grid(row=1, column=0, sticky="ew")
        image_cell = ttk.Frame(details)
        image_cell.grid(row=1, column=1, sticky="ew")
        ttk.Label(workspace_cell, text="Workspace").pack(anchor="w")
        self.workspace_box = ttk.Combobox(
            workspace_cell, textvariable=self.workspace, state="readonly", width=12
        )
        self.workspace_box.pack(fill="x", pady=(3, 10))
        ttk.Label(image_cell, text="Installed test environment").pack(anchor="w")
        self.image_box = ttk.Combobox(
            image_cell, textvariable=self.image, state="readonly", width=12
        )
        self.image_box.pack(fill="x", pady=(3, 10))
        for label, variable in (
            ("Allowed committed files (comma-separated patterns)", self.patterns),
            ("Test command inside the selected environment", self.command),
        ):
            ttk.Label(scope, text=label, wraplength=400).pack(anchor="w")
            ttk.Entry(scope, textvariable=variable).pack(fill="x", pady=(3, 12))
        ttk.Checkbutton(
            scope, text="Allow applying my reviewed changes", variable=self.allow_apply
        ).pack(anchor="w")
        ttk.Label(
            scope,
            text=(
                "Tests run offline in an existing container. Project files remain"
                " unchanged until you explicitly apply a reviewed patch."
            ),
            wraplength=400,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=12)
        self.save_button = ttk.Button(
            editor, text="Check and save project", command=self.save, state="disabled"
        )
        self.save_button.pack(side="bottom", before=tabs, anchor="e", pady=(12, 0))
        ttk.Label(frame, textvariable=self.status, wraplength=650, style="Muted.TLabel").pack(
            side="bottom", before=panes, anchor="w", pady=(12, 0)
        )
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
        path = filedialog.askdirectory(parent=self.app.root, title="Choose your Git project")
        if path:
            from pathlib import Path

            self.folder.set(path)
            self.name.set(Path(path).name)

    def editable(self) -> bool:
        if self.app.controller and self.app.controller.running:
            messagebox.showinfo(
                "Pause first",
                "Pause the worker, then save project changes. Resume afterward to publish them.",
                parent=self.app.root,
            )
            return False
        return True

    def refresh_projects(self) -> None:
        selected = self.projects.selection()
        self.projects.delete(*self.projects.get_children())
        for repo in self.app.settings.repositories:
            self.projects.insert(
                "",
                tk.END,
                iid=str(repo.id),
                values=(
                    repo.name,
                    "Needs attention"
                    if str(repo.id) in self.app.project_issues
                    else "Ready"
                    if self.app.projects_checked
                    else "Check on Resume",
                    "Apply enabled" if repo.allow_apply else "Preview only",
                ),
            )
        if selected and self.projects.exists(selected[0]):
            self.projects.selection_set(selected)
        self.selected_readiness()

    def selected_readiness(self, _event: object = None) -> None:
        selected = self.projects.selection()
        repository = next(
            (r for r in self.app.settings.repositories if selected and str(r.id) == selected[0]),
            None,
        )
        code = self.app.project_issues.get(str(repository.id)) if repository else None
        self.readiness.set(
            project_issue_message(repository, code)
            if repository and code and code in PROJECT_ISSUES
            else "Pause and Resume to check saved project dependencies. "
            "Unavailable projects stay saved and are withheld from coding jobs."
        )

    def toggle_apply(self) -> None:
        selected = self.projects.selection()
        if selected and self.editable():
            repositories = list(self.app.settings.repositories)
            index = self.projects.index(selected[0])
            repo = repositories[index]
            repositories[index] = repo.model_copy(update={"allow_apply": not repo.allow_apply})
            self.persist(repositories)

    def persist(self, repositories: list[CodingRepository]) -> None:
        if not self.editable():
            return
        settings = self.app.settings.model_copy(update={"repositories": repositories})
        save_settings(self.app.folder / "settings.json", settings)
        self.app.settings = settings
        self.app.show_project_readiness(
            [
                {"repository_id": identity, "code": code}
                for identity, code in self.app.project_issues.items()
            ]
        )
        self.refresh_projects()
        self.status.set(
            "Saved. Resume the worker, then refresh the repository list in Command Center."
        )

    def remove(self) -> None:
        selected = self.projects.selection()
        if selected and self.editable():
            repositories = list(self.app.settings.repositories)
            repositories.pop(self.projects.index(selected[0]))
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
