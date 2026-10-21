"""Native Tk/tray lifecycle smoke with synthetic identity and controller only."""

import argparse
import json
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

from godfather_contracts.coding import CodingSetupOptions, CodingWorkspace
from godfather_worker.coding_projects import Projects
from godfather_worker.desktop_app import Application
from godfather_worker.simulated import profile


def check(screenshot: Path | None = None, *, saved: bool = False) -> None:
    identity = {
        "kind": "worker",
        "token": "synthetic-only",
        "origin": "https://example.invalid",
        "owner": "test@example.invalid",
        "owner_id": "00000000-0000-0000-0000-000000000001",
        "name": "Test computer",
    }
    store = Mock()
    store.read.return_value = json.dumps(identity) if saved else None
    store.write.side_effect = AssertionError("Real enrollment is not part of UI smoke")
    controllers: list[Mock] = []

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
        patch("godfather_worker.desktop_app.discover_models", new=Mock()),
        patch("godfather_worker.desktop_app.Controller", side_effect=controller),
        patch("godfather_worker.desktop_app.await_approval", return_value=identity),
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
    ):

        async def models(*_: object) -> list[object]:
            return []

        with patch("godfather_worker.desktop_app.discover_models", models):
            app = Application(root, Path(folder))
            # Native tray creation is real; never contact a coordinator or credential store.
            assert app.tray is not None, "Native tray integration unavailable"
            deadline = threading.Event()

            def loaded() -> None:
                if app.connect_button["state"] == "disabled":
                    root.after(30, loaded)
                    return
                app.connect()
                root.after(30, connected)

            def connected() -> None:
                if app.status.get() != "Connected":
                    root.after(30, connected)
                    return
                assert app.identity == identity and len(controllers) == 1
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
                assert root.winfo_width() == expanded_width
                assert root.winfo_height() == expanded_height
                app.pause()
                root.after(130, paused)

            def paused() -> None:
                assert app.status.get() == "Paused"
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
                    assert app.settings.repositories[0].allowed_user_ids == [
                        UUID(identity["owner_id"])
                    ]
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
                    app.advanced()
                    dialog = app.settings_dialog
                    assert len(dialog.notebook.tabs()) == 6
                    dialog.values["theme"].set("dark")
                    dialog.save()
                    assert app.preferences.theme == "dark"
                    assert not dialog.window.winfo_exists()
                    app.advanced()
                    dialog = app.settings_dialog
                    dialog.notebook.select(dialog.pages["Workloads"])
                    root.update()
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
                    result.append(
                        "pairing, tray restore, expanded resizing, embedded Projects, "
                        "tabbed Settings, theme persistence and project permissions"
                    )
                    deadline.set()
                    app.quit()

                root.after(30, add_project)

            def expired() -> None:
                if not deadline.is_set():
                    app.quit()

            root.after(30, connected if saved else loaded)
            root.after(15000, expired)
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
