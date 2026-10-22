"""User-initiated macOS install/upgrade from the mounted Consigliere DMG."""

import plistlib
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from godfather_worker.native_desktop import acquire_lock, data_folder

BUNDLE_ID = "ai.the-godfather.worker"


def check_bundle(path: Path) -> None:
    if (
        path.is_symlink()
        or plistlib.loads((path / "Contents/Info.plist").read_bytes()).get("CFBundleIdentifier")
        != BUNDLE_ID
    ):
        raise OSError("Unrecognized app; refusing to replace it")


def install(source: Path, applications: Path) -> Path:
    """Fixed app name; retain the existing Keychain/data folder and startup consent."""
    check_bundle(source)
    applications.mkdir(parents=True, exist_ok=True)
    if applications.is_symlink():
        raise OSError("Applications folder must not be a symlink")
    destination = applications / "Consigliere.app"
    old = applications / "The Godfather Worker.app"
    for app in (destination, old):
        if app.exists():
            check_bundle(app)
    with TemporaryDirectory(prefix=".consigliere-install-", dir=applications) as temporary:
        staged = Path(temporary) / "Consigliere.app"
        # Preserve framework symlinks; remove only fixed, verified app bundles.
        shutil.copytree(source, staged, symlinks=True)
        backup = Path(temporary) / "previous.app"
        if destination.exists():
            destination.rename(backup)
        try:
            staged.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise
        if old.exists():
            shutil.rmtree(old)
    return destination


def main() -> int:
    import tkinter as tk
    from tkinter import ttk

    source = Path(sys.executable).resolve().parents[2]
    if "--auto-update" in sys.argv:
        import subprocess

        from godfather_worker.updates import update_failure, wait_for_previous

        lock = None
        try:
            wait_for_previous()
            lock = acquire_lock(data_folder())
            if lock is None:
                raise OSError("Worker is still running; update was not applied")
            target = next(
                (
                    p
                    for p in (Path("/Applications"), Path.home() / "Applications")
                    if (p / "Consigliere.app").exists()
                ),
                Path.home() / "Applications",
            )
            app = install(source, target)
            agent = Path.home() / "Library/LaunchAgents/ai.the-godfather.worker.plist"
            if agent.is_file():
                from godfather_worker.desktop import login_startup

                login_startup(True, app / "Contents/MacOS/Consigliere", agent)
            subprocess.Popen(["/usr/bin/open", str(app)])
        except Exception:
            return update_failure()
        finally:
            if lock is not None:
                lock.close()
        return 0
    root = tk.Tk()
    root.title("Install Consigliere — The Godfather AI")
    root.configure(background="#F4F8FC")
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Consigliere  /  The Godfather AI", font=("Helvetica", 20, "bold")).pack(
        anchor="w"
    )
    ttk.Label(
        frame,
        text="Quit the running worker from its tray menu before upgrading.\n"
        "Saved connection and project settings are preserved.",
        wraplength=500,
    ).pack(pady=16)
    status = tk.StringVar(value="Ready to install")
    ttk.Label(frame, textvariable=status, wraplength=500).pack()

    def start() -> None:
        lock = acquire_lock(data_folder())
        if lock is None:
            status.set("Quit Consigliere (or The Godfather Worker) from its tray menu, then retry.")
            return
        try:
            user_apps = Path.home() / "Applications"
            # Upgrade the existing installation in place, including the former name.
            system_apps = Path("/Applications")
            target = next(
                (
                    p
                    for p in (system_apps, user_apps)
                    if any(
                        (p / n).exists() for n in ("Consigliere.app", "The Godfather Worker.app")
                    )
                ),
                user_apps,
            )
            launch_agent = Path.home() / "Library/LaunchAgents/ai.the-godfather.worker.plist"
            startup = launch_agent.is_file()
            app = install(source, target)
            if startup:
                from godfather_worker.desktop import login_startup

                login_startup(True, app / "Contents/MacOS/Consigliere", launch_agent)
            status.set(
                "Installed. Open Consigliere from Applications. You can eject the installer disk."
            )
            button.configure(state="disabled")
        except (OSError, ValueError) as error:
            status.set(
                f"Installation incomplete: {error}. "
                "Check Applications folder permissions and retry."
            )
        finally:
            lock.close()

    button = ttk.Button(frame, text="Install / replace existing version", command=start)
    button.pack(pady=16)
    root.mainloop()
    return 0
