"""Native Jobs tab and actionable notification center, driven by confirmed activity."""

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from uuid import UUID

from godfather_contracts.shared_engine import EngineGroup
from godfather_contracts.worker_activity import ActivityRequest, ActivityResponse, NodeJob

from godfather_worker.activity import Inbox, Notice, inbox_path, load_inbox, save_inbox
from godfather_worker.client import WorkerClient

if TYPE_CHECKING:
    from godfather_worker.desktop_app import Application


def local_time(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S") if value else "-"


class Activity:
    def __init__(self, app: "Application", jobs: ttk.Frame, notifications: ttk.Frame) -> None:
        self.app = app
        self.inbox = Inbox()
        self.path: Path | None = None
        self.busy = False
        self.offset = 0
        self.job_id: UUID | None = None
        self.rows: dict[str, NodeJob] = {}
        self.status = tk.StringVar(value="Connect this computer to view its jobs.")
        self.detail = tk.StringVar(value="Select a job to view its execution details.")
        self.notice_detail = tk.StringVar(value="Select a notification, then Open to review it.")
        controls = ttk.Frame(jobs, padding=12)
        controls.grid(row=0, column=0, sticky="ew")
        ttk.Button(controls, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(controls, text="Show all jobs", command=self.all_jobs).pack(side="left", padx=6)
        self.previous = ttk.Button(controls, text="Previous 25", command=lambda: self.page(-25))
        self.previous.pack(side="left", padx=6)
        self.next = ttk.Button(controls, text="Next 25", command=lambda: self.page(25))
        self.next.pack(side="left")
        ttk.Label(jobs, textvariable=self.status, wraplength=700, padding=(12, 0)).grid(
            row=1, column=0, sticky="ew"
        )
        self.table = self.table_widget(
            jobs,
            [
                ("job", "Job", 100),
                ("type", "Type", 160),
                ("status", "This attempt", 110),
                ("workspace", "Workspace", 150),
                ("attempt", "Attempt", 60),
                ("started", "Started (local time)", 160),
                ("finished", "Finished (local time)", 160),
            ],
            row=2,
        )
        self.table.bind("<<TreeviewSelect>>", self.selection)
        self.job_detail_label = ttk.Label(
            jobs, textvariable=self.detail, wraplength=850, padding=12
        )
        self.job_detail_label.grid(row=3, column=0, sticky="ew")
        self.job_help = ttk.Label(
            jobs,
            text="History comes from Command Center. Includes shared jobs this computer "
            "contributed to. Each retry is a separate attempt. "
            "Prompts and results stay in Command Center.",
            wraplength=850,
            padding=(12, 0, 12, 8),
            style="Muted.TLabel",
        )
        self.job_help.grid(row=4, column=0, sticky="ew")
        commands = ttk.Frame(notifications, padding=12)
        commands.grid(row=0, column=0, sticky="ew")
        ttk.Button(commands, text="Open selected", command=self.open_selected).pack(side="left")
        ttk.Button(commands, text="Mark selected read", command=self.mark_selected).pack(
            side="left", padx=6
        )
        ttk.Button(commands, text="Mark all read", command=self.mark_all).pack(side="left")
        self.notices = self.table_widget(
            notifications,
            [
                ("read", "", 65),
                ("time", "Time (local)", 160),
                ("title", "Notification", 480),
            ],
            row=1,
        )
        self.notices.bind("<<TreeviewSelect>>", self.notice_selection)
        self.notices.bind("<Double-1>", lambda _: self.open_selected())
        self.notice_detail_label = ttk.Label(
            notifications, textvariable=self.notice_detail, wraplength=850, padding=12
        )
        self.notice_detail_label.grid(row=2, column=0, sticky="ew")
        self.notice_help = ttk.Label(
            notifications,
            text="The latest 200 notifications are saved on this computer. "
            "Opening a notice does not approve participation or start a job.",
            wraplength=850,
            padding=12,
            style="Muted.TLabel",
        )
        self.notice_help.grid(row=3, column=0, sticky="ew")
        for label in (
            self.job_detail_label,
            self.job_help,
            self.notice_detail_label,
            self.notice_help,
        ):
            label.bind(
                "<Configure>",
                lambda event: event.widget.configure(wraplength=max(100, event.width - 24)),
            )
        self.timer = app.root.after(1000, self.tick)
        self.render_notices()

    def table_widget(
        self, parent: ttk.Frame, columns: list[tuple[str, str, int]], *, row: int
    ) -> ttk.Treeview:
        frame = ttk.Frame(parent, padding=12)
        frame.grid(row=row, column=0, sticky="nsew")
        parent.rowconfigure(row, weight=1)
        parent.columnconfigure(0, weight=1)
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=8)
        for name, title, width in columns:
            table.heading(name, text=title)
            table.column(name, width=width, minwidth=55)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return table

    def scope(self) -> bool:
        account = self.app.identity
        path = (
            inbox_path(self.app.folder, account)
            if account and account.get("credential_id")
            else None
        )
        if path != self.path:
            self.path = path
            self.inbox = load_inbox(path) if path else Inbox()
            self.offset, self.job_id = 0, None
            self.rows = {}
            self.table.delete(*self.table.get_children())
            self.detail.set("Select a job to view its execution details.")
            self.app.notebook.tab(self.app.shared_tab, text="Shared Inference")  # type: ignore[no-untyped-call]
            self.render_notices()
        return path is not None

    def persist(self) -> None:
        if self.path:
            try:
                save_inbox(self.path, self.inbox)
            except OSError:
                self.status.set(
                    "Activity is current, but local notification history could not be saved."
                )

    def tick(self) -> None:
        if self.app.closing:
            return
        self.refresh()
        self.timer = self.app.root.after(5000, self.tick)

    def close(self) -> None:
        self.app.root.after_cancel(self.timer)

    def refresh(self) -> None:
        if self.app.closing or self.busy:
            return
        if not self.scope():
            self.status.set("Connect this computer to view its jobs.")
            return
        account = dict(self.app.identity or {})
        request = ActivityRequest(offset=self.offset, job_id=self.job_id, cursor=self.inbox.cursor)
        self.busy = True
        self.status.set("Refreshing this computer's jobs...")

        def work() -> None:
            result = None
            error = ""
            try:
                client = WorkerClient(account["origin"], account["token"])
                result = ActivityResponse.model_validate(
                    client.post_document("/api/v1/workers/activity/jobs", request)
                )
            except HTTPError as failure:
                error = (
                    "Jobs requires the matching Command Center update."
                    if failure.code == 404
                    else "Jobs is unavailable. Check this computer's connection and permissions."
                )
            except (OSError, ValueError):
                error = (
                    "Could not refresh jobs. Showing the last confirmed history; "
                    "retry when connected."
                )
            self.app.event(
                "activity_update", apply=lambda: self.received(account, request, result, error)
            )

        self.app.background(work)

    def received(
        self,
        account: dict[str, str],
        request: ActivityRequest,
        result: ActivityResponse | None,
        error: str,
    ) -> None:
        self.busy = False
        if self.app.closing or self.app.identity != account:
            return
        if result is None:
            self.status.set(error)
            return
        for event in result.events:
            self.inbox.job_event(event)
        self.inbox.cursor = result.cursor
        self.render_notices()
        if request.offset == self.offset and request.job_id == self.job_id:
            selected = self.table.selection()
            self.rows = {str(row.attempt_id): row for row in result.jobs}
            self.table.delete(*self.table.get_children())
            for key, row in self.rows.items():
                self.table.insert(
                    "",
                    "end",
                    iid=key,
                    values=(
                        str(row.job_id)[:8],
                        row.type + (" (shared)" if row.shared else ""),
                        row.status.capitalize(),
                        row.workspace,
                        row.number,
                        local_time(row.started_at),
                        local_time(row.finished_at),
                    ),
                )
            if selected and selected[0] in self.rows:
                self.table.selection_set(selected[0])
            self.previous.configure(state="normal" if self.offset else "disabled")
            self.next.configure(state="normal" if result.has_more else "disabled")
            self.status.set(
                f"Showing {self.offset + 1}-{self.offset + len(result.jobs)}. "
                f"Updated {datetime.now().strftime('%H:%M:%S')}."
                if result.jobs
                else "No recorded executions for this computer in your current workspaces."
            )
            self.selection()
        self.persist()
        if result.more_events:
            self.app.root.after(100, self.refresh)

    def selection(self, _: object = None) -> None:
        selected = self.table.selection()
        row = self.rows.get(selected[0]) if selected else None
        self.detail.set(
            f"Job {row.job_id}\nAttempt {row.number}: {row.status}. Overall job: {row.job_status}. "
            f"Assigned {local_time(row.created_at)}."
            if row
            else "Select a job to view its execution details."
        )

    def page(self, change: int) -> None:
        if not self.busy:
            self.offset = max(0, self.offset + change)
            self.refresh()

    def all_jobs(self) -> None:
        if not self.busy:
            self.offset, self.job_id = 0, None
            self.refresh()

    def render_notices(self) -> None:
        selected = self.notices.selection()
        self.notices.delete(*self.notices.get_children())
        for notice in self.inbox.notices:
            self.notices.insert(
                "",
                "end",
                iid=str(notice.id),
                values=(
                    "Read" if notice.read else "NEW",
                    local_time(notice.at),
                    notice.title,
                ),
            )
        if selected and any(str(n.id) == selected[0] for n in self.inbox.notices):
            self.notices.selection_set(selected[0])
        unread = sum(not n.read for n in self.inbox.notices)
        caption = f"Notifications ({unread})" if unread else "Notifications"
        self.app.notebook.tab(self.app.notifications_tab, text=caption)  # type: ignore[no-untyped-call]
        self.app.notifications_button.configure(text=caption)
        newest = next((n for n in self.inbox.notices if not n.read), None)
        self.app.notification_summary.set(
            newest.title + ". Open Notifications to review." if newest else "No new notifications."
        )
        self.notice_selection()

    def selected_notice(self) -> Notice | None:
        selected = self.notices.selection()
        return next((n for n in self.inbox.notices if selected and str(n.id) == selected[0]), None)

    def notice_selection(self, _: object = None) -> None:
        notice = self.selected_notice()
        self.notice_detail.set(
            notice.message if notice else "Select a notification, then Open to review it."
        )

    def mark_selected(self) -> None:
        notice = self.selected_notice()
        if notice:
            notice.read = True
            self.render_notices()
            self.persist()

    def mark_all(self) -> None:
        for notice in self.inbox.notices:
            notice.read = True
        self.render_notices()
        self.persist()

    def open_selected(self) -> None:
        notice = self.selected_notice()
        if not notice:
            return
        self.mark_selected()
        if notice.target == "shared":
            self.app.notebook.select(self.app.shared_tab)  # type: ignore[no-untyped-call]
            panel = self.app.shared_inference
            if str(notice.reference) in panel.groups:
                panel.table.selection_set(str(notice.reference))
                panel.selection()
            else:
                panel.message.set(
                    "This setup is no longer in the current invitations. Refresh to check."
                )
        else:
            self.app.notebook.select(self.app.jobs_tab)  # type: ignore[no-untyped-call]
            self.offset, self.job_id = 0, notice.reference
            self.refresh()

    def shared_groups(self, node_id: UUID, groups: list[EngineGroup]) -> None:
        if not self.scope():
            return
        count = self.inbox.shared_groups(node_id, groups)
        self.app.notebook.tab(
            self.app.shared_tab, text=f"Shared Inference ({count})" if count else "Shared Inference"
        )  # type: ignore[no-untyped-call]
        self.render_notices()
        self.persist()
