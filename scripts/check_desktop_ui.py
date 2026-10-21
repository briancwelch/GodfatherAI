"""Native Tk/tray lifecycle smoke with synthetic identity and controller only."""

import argparse
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock, patch

from godfather_worker.desktop_app import Application
from godfather_worker.simulated import profile


def check(screenshot: Path | None = None) -> None:
    identity = {
        "kind": "worker",
        "token": "synthetic-only",
        "origin": "https://example.invalid",
        "owner": "test@example.invalid",
        "name": "Test computer",
    }
    store = Mock()
    store.read.return_value = None
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
    with (
        tempfile.TemporaryDirectory() as folder,
        patch("godfather_worker.desktop_app.CredentialStore", return_value=store),
        patch("godfather_worker.desktop_app.discover", return_value=profile("LV-01")),
        patch("godfather_worker.desktop_app.discover_models", new=Mock()),
        patch("godfather_worker.desktop_app.Controller", side_effect=controller),
        patch("godfather_worker.desktop_app.await_approval", return_value=identity),
        patch("godfather_worker.desktop_app.webbrowser.open") as browser,
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
                app.show()
                app.pause()
                root.after(130, paused)

            def paused() -> None:
                assert app.status.get() == "Paused"
                app.start()
                assert len(controllers) == 2
                result.append("automatic pairing, start, tray hide/show, pause and resume")
                deadline.set()
                app.quit()

            def expired() -> None:
                if not deadline.is_set():
                    app.quit()

            root.after(30, loaded)
            root.after(15000, expired)
            root.mainloop()
    assert result, "Native desktop lifecycle did not complete"
    print("Passed native UI smoke: " + result[0] + "; quit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path)
    check(parser.parse_args().screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
