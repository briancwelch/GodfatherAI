"""Native Tk/tray lifecycle smoke with synthetic identity and controller only."""

import argparse
import json
import tempfile
import threading
import tkinter as tk
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from godfather_contracts.coding import CodingSetupOptions, CodingWorkspace
from godfather_contracts.shared_engine import EngineGroup, EngineMember, EngineProposal
from godfather_contracts.worker_activity import (
    ActivityCursor,
    ActivityRequest,
    ActivityResponse,
    JobNotice,
    NodeJob,
)
from godfather_worker.coding_projects import Projects
from godfather_worker.desktop_app import Application
from godfather_worker.simulated import profile


def check_activity(app: Application) -> None:
    """Exercise real widgets with confirmed synthetic data; never contact a coordinator."""
    assert app.identity
    panel = app.activity
    assert panel.scope()
    own, leader, job, attempt, group_id = (uuid4() for _ in range(5))
    now = datetime.now(UTC)
    completed = JobNotice(
        id=uuid4(), job_id=job, attempt_id=attempt, type="job.completed", created_at=now
    )
    panel.received(
        dict(app.identity),
        ActivityRequest(),
        ActivityResponse(
            node_id=own,
            jobs=[
                NodeJob(
                    job_id=job,
                    attempt_id=attempt,
                    type="inference.text",
                    workspace="Fixture",
                    status="COMPLETED",
                    job_status="COMPLETED",
                    number=1,
                    shared=True,
                    created_at=now,
                    started_at=now,
                    finished_at=now,
                )
            ],
            has_more=False,
            events=[completed],
            cursor=ActivityCursor(at=now, id=completed.id),
        ),
        "",
    )
    assert len(panel.table.get_children()) == 1
    assert str(app.notifications_button["text"]) == "Notifications (1)"
    panel.notices.selection_set(panel.notices.get_children()[0])
    panel.open_selected()
    assert app.notebook.select() == str(app.jobs_tab)  # type: ignore[no-untyped-call]
    assert panel.job_id == job
    group = EngineGroup(
        proposal=EngineProposal(
            id=group_id,
            workspace_id=uuid4(),
            name="LAN fixture",
            model_name="fixture.gguf",
            mode="local_network",
            leader_node_id=leader,
            node_ids=[leader, own],
        ),
        members=[
            EngineMember(node_id=leader, name="Leader", owner="Fixture", approved=True),
            EngineMember(node_id=own, name="This computer", owner="Fixture", approved=False),
        ],
        desired_running=False,
        generation=0,
    )
    app.shared_inference.received(own, [group])
    assert "approve and join" in app.notification_summary.get()
    panel.notices.selection_set(panel.notices.get_children()[0])
    panel.open_selected()
    assert app.notebook.select() == str(app.shared_tab)  # type: ignore[no-untyped-call]
    assert app.shared_inference.selected() == group
    assert not group.members[1].approved and not group.desired_running
    panel.table.selection_set(str(attempt))
    panel.selection()
    assert str(job) in panel.detail.get()
    for width, height in ((1120, 760), (760, 600)):
        app.root.geometry(f"{width}x{height}")
        for tab, widgets in (
            (app.jobs_tab, (panel.table, panel.job_detail_label, panel.job_help)),
            (app.notifications_tab, (panel.notices, panel.notice_detail_label, panel.notice_help)),
            (app.shared_tab, (app.shared_inference.approve_button,)),
        ):
            app.notebook.select(tab)  # type: ignore[no-untyped-call]
            app.root.update()
            for widget in widgets:
                assert widget.winfo_viewable()
                assert widget.winfo_rooty() + widget.winfo_height() <= (
                    app.root.winfo_rooty() + app.root.winfo_height()
                )
                if isinstance(widget, tk.ttk.Label):
                    assert widget.winfo_height() >= widget.winfo_reqheight()
    panel.mark_all()
    assert str(app.notifications_button["text"]) == "Notifications"


def check(screenshot: Path | None = None, *, saved: bool = False) -> None:
    identity = {
        "kind": "worker",
        "token": "synthetic-only",
        "origin": "https://example.invalid",
        "owner": "test@example.invalid",
        "owner_id": "00000000-0000-0000-0000-000000000001",
        "credential_id": "00000000-0000-0000-0000-000000000002",
        "name": "Test computer",
    }
    store = Mock()
    store.read.return_value = json.dumps(identity) if saved else None
    store.write.side_effect = AssertionError("Real enrollment is not part of UI smoke")
    controllers: list[Mock] = []
    approval_ready = threading.Event()

    def approve(*_: object) -> dict[str, str]:
        assert approval_ready.wait(10), "Pairing code was never presented"
        return identity

    def controller(*args: object) -> Mock:
        instance = Mock(running=False)

        def start(*_: object) -> None:
            instance.running = True
            app.event("worker.registered")

        def stop() -> None:
            instance.running = False
            app.event("worker.stopped")

        instance.start.side_effect, instance.stop.side_effect = start, stop
        controllers.append(instance)
        return instance

    root = tk.Tk()
    result: list[str] = []

    async def images(*_: object) -> dict[str, str]:
        return {"Fixture test environment": "sha256:" + "a" * 64}

    async def project_check(*_: object) -> None:
        pass

    with (
        tempfile.TemporaryDirectory() as folder,
        patch("godfather_worker.desktop_app.CredentialStore", return_value=store),
        patch("godfather_worker.desktop_app.discover", return_value=profile("LV-01")),
        patch("godfather_worker.shared_inference_ui.SharedInference.refresh", new=Mock()),
        patch("godfather_worker.activity_ui.Activity.refresh", new=Mock()),
        patch("godfather_worker.desktop_app.Controller", side_effect=controller),
        patch("godfather_worker.desktop_app.await_approval", side_effect=approve),
        patch("godfather_worker.desktop_app.webbrowser.open") as browser,
        patch(
            "godfather_worker.coding_projects.setup_options",
            return_value=CodingSetupOptions(
                owner_id=UUID(identity["owner_id"]),
                workspaces=[
                    CodingWorkspace(
                        id=UUID("00000000-0000-0000-0000-000000000002"), name="Fixture workspace"
                    )
                ],
            ),
        ),
        patch("godfather_worker.coding_projects.local_images", images),
        patch("godfather_worker.desktop_settings.local_images", images),
        patch("godfather_worker.coding_projects.check_project", project_check),
        patch(
            "godfather_worker.desktop_app.scan",
            side_effect=AssertionError("Scan requires an owner button click"),
        ),
    ):
        app = Application(root, Path(folder))
        # Native tray creation is real; never contact a coordinator or credential store.
        assert app.tray is not None, "Native tray integration unavailable"
        deadline = threading.Event()

        def loaded() -> None:
            if app.connect_button["state"] == "disabled":
                root.after(30, loaded)
                return
            app.connect()
            root.update_idletasks()
            assert app.connection_state.get() == "AWAITING APPROVAL"
            assert "Match this code" in app.code.get()
            from urllib.parse import urlsplit

            challenge = urlsplit(browser.call_args.args[0]).fragment.split("=", 1)[1]
            assert challenge[:12].upper() in app.code.get()
            if screenshot:
                from PIL import ImageGrab

                screenshot.parent.mkdir(parents=True, exist_ok=True)
                ImageGrab.grab(window=root.winfo_id()).save(
                    screenshot.with_stem(screenshot.stem + "-pairing")
                )
            approval_ready.set()
            root.after(30, connected)

        def connected() -> None:
            if not app.status.get().startswith("Connected"):
                root.after(30, connected)
                return
            assert app.identity == identity and len(controllers) == 1
            assert app.connection_state.get() == "CONNECTED"
            assert app.settings.share_with_workspaces is (not saved)
            assert app.contribute.get() is (not saved)
            assert not app.code.get()
            if saved:
                browser.assert_not_called()
            else:
                browser.assert_called_once()
            if screenshot:
                from PIL import ImageGrab

                root.update_idletasks()
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                import platform

                if platform.system() == "Windows":
                    ImageGrab.grab(window=root.winfo_id()).save(screenshot)
            app.hide()
            assert root.state() == "withdrawn"
            app.tray()  # Native tray activation invokes the default Show action.
            root.after(150, restored)

        def restored() -> None:
            assert root.state() == "normal"
            root.geometry("800x600")
            root.update()
            assert root.winfo_width() == 800
            expanded_width = min(1200, root.winfo_screenwidth() - 64)
            expanded_height = min(900, root.winfo_screenheight() - 96)
            root.geometry(f"{expanded_width}x{expanded_height}")
            root.update()
            # Cocoa may reduce the client height for its menu/dock/work area.
            # Verify useful expansion, rather than requiring Windows pixel parity.
            print(
                "Native resized client",
                root.winfo_width(),
                root.winfo_height(),
                "requested",
                expanded_width,
                expanded_height,
                flush=True,
            )
            assert root.winfo_width() >= expanded_width - 32
            assert root.winfo_height() >= min(600, expanded_height - 64)
            assert root.maxsize()[0] > 900
            app.pause()
            root.after(130, paused)

        def paused() -> None:
            assert app.status.get() == "Paused"
            assert app.connection_state.get() == "PAUSED"
            app.projects()
            project = app.project_editor
            assert isinstance(project, Projects)
            assert not isinstance(project.window, tk.Toplevel)

            def add_project() -> None:
                if project.options is None:
                    root.after(30, add_project)
                    return
                project.name.set("Fixture project")
                project.folder.set(folder)
                project.patterns.set("src/*.py")
                project.command.set("python -m unittest")
                project.save()
                root.after(30, saved_project)

            def saved_project() -> None:
                if not app.settings.repositories:
                    root.after(30, saved_project)
                    return
                assert app.settings.repositories[0].allowed_user_ids == [UUID(identity["owner_id"])]
                repo = app.settings.repositories[0]
                app.show_project_readiness(
                    [{"repository_id": str(repo.id), "code": "image_missing"}]
                )
                app.notebook.select(0)  # type: ignore[no-untyped-call]
                root.update()
                assert app.project_notice.winfo_ismapped()
                assert "image is missing" in app.project_warning.get()
                if screenshot:
                    from PIL import ImageGrab

                    ImageGrab.grab(window=root.winfo_id()).save(
                        screenshot.with_stem(screenshot.stem + "-project-warning")
                    )
                app.projects()
                project.projects.selection_set(str(repo.id))
                project.selected_readiness()
                assert repo.image in project.readiness.get()
                root.update()
                if screenshot:
                    from PIL import ImageGrab

                    ImageGrab.grab(window=root.winfo_id()).save(
                        screenshot.with_stem(screenshot.stem + "-projects")
                    )
                root.geometry("800x600")
                root.update()
                assert (
                    project.save_button.winfo_rooty() + project.save_button.winfo_height()
                    <= root.winfo_rooty() + root.winfo_height()
                )
                app.show_project_readiness([])
                assert not app.project_notice.winfo_ismapped()
                app.advanced()
                dialog = app.settings_dialog
                assert len(dialog.notebook.tabs()) == 6
                assert "owners" not in dialog.values and "workspaces" not in dialog.values
                assert "share_with_workspaces" in dialog.values
                assert not dialog.values["model_installation"].get()
                dialog.values["inference"].set(False)
                dialog.values["model_installation"].set(True)
                dialog.save()
                assert "Enable local AI models" in dialog.status.get()
                assert dialog.window.winfo_exists()
                assert not app.settings.model_installation
                dialog.values["inference"].set(True)
                dialog.values["theme"].set("dark")
                dialog.save()
                assert app.preferences.theme == "dark"
                assert app.settings.model_installation and app.model_installation.get()
                assert json.loads((app.folder / "settings.json").read_text())["model_installation"]
                assert not dialog.window.winfo_exists()
                app.advanced()
                dialog = app.settings_dialog
                dialog.notebook.select(dialog.pages["Resources"])
                root.update()
                page = dialog.pages["Resources"]
                for child in page.winfo_children():
                    assert child.winfo_y() + child.winfo_height() <= page.winfo_height()
                if screenshot:
                    ImageGrab.grab(window=dialog.window.winfo_id()).save(
                        screenshot.with_stem(screenshot.stem + "-settings")
                    )
                dialog.window.destroy()
                project.projects.selection_set(project.projects.get_children()[0])
                assert not app.settings.repositories[0].allow_apply
                project.toggle_apply()
                assert app.settings.repositories[0].allow_apply
                project.projects.selection_set(project.projects.get_children()[0])
                project.toggle_apply()
                assert not app.settings.repositories[0].allow_apply
                project.projects.selection_set(project.projects.get_children()[0])
                project.remove()
                assert not app.settings.repositories
                # Projects remains embedded in the main notebook.
                app.start()
                assert len(controllers) == 2
                assert not app.models  # First-model downloads must not block Resume.
                assert controllers[-1].start.call_args.args[0].model_installation
                app.model_installation.set(False)
                app.apply_models()
                assert not app.model_installation.get()
                assert app.settings_restart_pending
                app.advanced()
                dialog = app.settings_dialog
                dialog.values["model_installation"].set(False)
                dialog.save()
                assert not dialog.window.winfo_exists()
                assert not app.settings.model_installation
                assert app.settings_restart_pending
                controllers[-1].maintenance_event.set.assert_called_once()
                app.pause()
                app.advanced()
                dialog = app.settings_dialog
                dialog.values["model_installation"].set(False)
                dialog.save()
                assert not app.settings.model_installation
                assert not app.model_installation.get()
                app.start()
                assert not controllers[-1].start.call_args.args[0].model_installation
                app.contribute.set(True)
                app.apply_contribution()
                assert app.settings.share_with_workspaces and app.settings.inference
                assert app.settings_restart_pending
                assert not app.settings.allowed_owner_ids
                assert not app.settings.allowed_workspace_ids
                check_activity(app)
                result.append(
                    "pairing, tray restore, expanded resizing, embedded Projects, "
                    "tabbed Settings, theme persistence, project permissions, "
                    "model-download consent, ID-free contribution, idle-safe updates, "
                    "node Jobs and actionable notifications at desktop/compact sizes"
                )
                deadline.set()
                app.quit()

            root.after(30, add_project)

        def expired() -> None:
            if not deadline.is_set():
                app.quit()

        root.after(30, connected if saved else loaded)
        # Intel hosted Macs can spend >15s in Cocoa window/tray activation.
        # This is an overall safety deadline, never a sleep or success condition.
        root.after(60000, expired)
        root.mainloop()
    assert result, "Native desktop lifecycle did not complete"
    print("Passed native UI smoke: " + result[0] + "; quit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path)
    check(parser.parse_args().screenshot)
    check(saved=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
