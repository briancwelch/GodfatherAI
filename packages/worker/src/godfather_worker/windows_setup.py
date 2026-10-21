"""Per-user desktop setup. Copies only bundled application files, never credentials."""

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from godfather_worker.app_installation import (
    contained_directory,
    legacy_windows_versions,
    replace_payload,
)
from godfather_worker.native_desktop import acquire_lock


def install(payload: Path, local: Path, programs: Path) -> Path:
    manifest = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    import re

    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?", version):
        raise ValueError("Invalid installer version")
    base = local / "The Godfather" / "Desktop Worker"
    contained_directory(base, local)
    base.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(base)
    if lock is None:
        raise OSError("Quit Consigliere (or The Godfather Worker) from its tray menu, then retry.")
    try:
        legacy = legacy_windows_versions(base)
        destination = base / "app"
        if destination.exists():
            installed = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
            if installed.get("version") == version:
                for source in payload.rglob("*"):
                    if source.is_file():
                        target = destination / source.relative_to(payload)
                        if not target.is_file() or target.read_bytes() != source.read_bytes():
                            raise OSError("This version is already installed with different files")
        replace_payload(payload, destination)
        executable = destination / (
            "consigliere.exe" if (payload / "consigliere.exe").is_file() else "godfather-worker.exe"
        )
        create_shortcut(programs, executable)
        update_startup(base, executable)
        for path in legacy:
            shutil.rmtree(path)
        legacy_shortcut = programs / "The Godfather Worker.lnk"
        if legacy_shortcut.is_file():
            legacy_shortcut.unlink()
        return executable
    finally:
        lock.close()


def update_startup(base: Path, executable: Path) -> None:
    registry = importlib.import_module("winreg")

    with registry.CreateKey(
        registry.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        try:
            value, _ = registry.QueryValueEx(key, "The Godfather Worker")
        except FileNotFoundError:
            return
        # Preserve the user's existing opt-in; never add autostart during installation.
        if isinstance(value, str) and value.startswith('"'):
            old = Path(value.split('"')[1])
            if old.resolve().is_relative_to(base.resolve()):
                registry.SetValueEx(
                    key, "The Godfather Worker", 0, registry.REG_SZ, f'"{executable}" --login'
                )


def create_shortcut(programs: Path, executable: Path) -> None:
    programs.mkdir(parents=True, exist_ok=True)
    shortcut = programs / "Consigliere.lnk"
    # Values are passed as environment data, never interpolated into PowerShell code.
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:GODFATHER_SETUP_LINK);"
            "$s.TargetPath=$env:GODFATHER_SETUP_TARGET;"
            "$s.WorkingDirectory=[IO.Path]::GetDirectoryName($env:GODFATHER_SETUP_TARGET);"
            "$s.Save()",
        ],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={
            **os.environ,
            "GODFATHER_SETUP_LINK": str(shortcut),
            "GODFATHER_SETUP_TARGET": str(executable),
        },
    )


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    payload = Path(getattr(sys, "_MEIPASS", "")) / "worker-payload"
    if "--self-test" in sys.argv:
        with TemporaryDirectory(prefix="godfather-setup-smoke-") as temporary:
            folder = Path(temporary)
            executable = install(payload, folder / "local", folder / "programs")
            subprocess.run([str(executable), "--self-test"], check=True, timeout=30)
            assert (folder / "programs/Consigliere.lnk").is_file()
            assert install(payload, folder / "local", folder / "programs") == executable
        return 0
    root = tk.Tk()
    root.title("Install Consigliere — The Godfather AI")
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Consigliere  /  The Godfather AI", font=("Segoe UI", 20, "bold")).pack(
        anchor="w"
    )
    ttk.Label(
        frame,
        text="Install for your Windows account. No administrator password needed.\n"
        "Then connect using your Command Center address and invited Google account.",
        wraplength=450,
    ).pack(anchor="w", pady=18)
    status = tk.StringVar(value="Ready to install")
    ttk.Label(frame, textvariable=status, wraplength=450).pack(anchor="w", pady=8)

    def start() -> None:
        button.configure(state="disabled")
        status.set("Installing...")
        root.update_idletasks()
        try:
            executable = install(
                payload,
                Path(os.environ["LOCALAPPDATA"]),
                Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs",
            )
            subprocess.Popen(
                [str(executable)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            root.destroy()
        except Exception as error:
            status.set(
                f"Installation did not finish: {error}. "
                "Close Consigliere from its tray menu and retry. "
                "Existing worker identities and data were preserved."
            )
            button.configure(state="normal")
            messagebox.showerror("Installation incomplete", status.get())

    button = ttk.Button(frame, text="Install and open", command=start)
    button.pack(anchor="w", pady=12)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
