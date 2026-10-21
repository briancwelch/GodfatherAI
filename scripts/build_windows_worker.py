"""Build the per-user Windows setup executable, without installing or launching it."""

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path

from scripts import build_worker
from scripts.dev import ROOT
from scripts.release import sha256, version


def build(release: str) -> Path:
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Build on a native Windows x64 host")
    output = ROOT / "dist" / f"godfather-worker-{release}-windows-x64-setup.exe"
    if output.exists():
        raise RuntimeError("Installer already exists; use a new version")
    build_worker.build(release)
    workspace = ROOT / ".cache/worker-build" / f"{release}-windows-x64"
    payload = ROOT / "dist" / f"godfather-worker-{release}-windows-x64"
    entry = workspace / "setup-entry.py"
    entry.write_text("from godfather_worker.windows_setup import main\nraise SystemExit(main())\n")
    subprocess.run(
        [
            str(workspace / ".venv/Scripts/python.exe"),
            "-m",
            "PyInstaller",
            "--onefile",
            "--windowed",
            "--clean",
            "--noconfirm",
            "--name",
            output.stem,
            "--distpath",
            str(output.parent),
            "--workpath",
            str(workspace / "setup-build"),
            "--specpath",
            str(workspace),
            "--add-data",
            f"{payload}{os.pathsep}worker-payload",
            "--exclude-module",
            "pytest",
            "--exclude-module",
            "pip",
            str(entry),
        ],
        cwd=ROOT,
        check=True,
    )
    Path(str(output) + ".sha256").write_text(f"{sha256(output)}  {output.name}\n")
    Path(str(output) + ".manifest.json").write_text(
        json.dumps(
            {
                "version": release,
                "source_revision": json.loads((payload / "manifest.json").read_text())[
                    "source_revision"
                ],
                "signing": "Unsigned Windows candidate; SmartScreen acceptance not claimed",
                "installation": "Per-user app and Start menu shortcut; no elevation or services",
            },
            indent=2,
        )
        + "\n"
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=version)
    print(build(parser.parse_args().version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
