"""Per-user desktop setup. Copies only bundled application files, never credentials."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def install(payload: Path, local: Path, programs: Path) -> Path:
    manifest = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    import re

    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?", version):
        raise ValueError("Invalid installer version")
    destination = local / "The Godfather" / "Desktop Worker" / "versions" / version
    executable = destination / "godfather-worker.exe"
    # Idempotent installation requires byte-identical files. Never overwrite a
    # running build or recursively remove an existing version.
    if destination.exists():
        for source in payload.rglob("*"):
            if source.is_file():
                target = destination / source.relative_to(payload)
                if not target.is_file() or target.read_bytes() != source.read_bytes():
                    raise OSError("This version is already installed with different files")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".install-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "payload"
            shutil.copytree(payload, staged)
            staged.rename(destination)
    programs.mkdir(parents=True, exist_ok=True)
    shortcut = programs / "The Godfather Worker.lnk"
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
    return executable


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    payload = Path(getattr(sys, "_MEIPASS", "")) / "worker-payload"
    if "--self-test" in sys.argv:
        with TemporaryDirectory(prefix="godfather-setup-smoke-") as temporary:
            folder = Path(temporary)
            executable = install(payload, folder / "local", folder / "programs")
            subprocess.run([str(executable), "--self-test"], check=True, timeout=30)
            assert (folder / "programs/The Godfather Worker.lnk").is_file()
            assert install(payload, folder / "local", folder / "programs") == executable
        return 0
    root = tk.Tk()
    root.title("Install The Godfather Worker")
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="The Godfather Worker", font=("Segoe UI", 20, "bold")).pack(anchor="w")
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
        except Exception:
            status.set(
                "Installation did not finish. Close other setup windows and retry. "
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
