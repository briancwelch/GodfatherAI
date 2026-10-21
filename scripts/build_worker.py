"""Build only the standalone worker for the current OS/architecture; never installs it."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

from scripts.dev import ROOT
from scripts.release import sha256, source_revision, version

PYINSTALLER = "6.22.3"


def target() -> str:
    system = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[platform.system()]
    machine = platform.machine().lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}
    if machine not in architecture:
        raise RuntimeError("Unsupported native build architecture")
    return f"{system}-{architecture[machine]}"


def build(release: str) -> Path:
    native = target()
    destination = ROOT / "dist" / f"consigliere-{release}-{native}"
    archive = Path(str(destination) + ".zip")
    if destination.exists() or archive.exists():
        raise RuntimeError("Worker output already exists; use a new release version")
    revision = source_revision()
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Build prerequisite: uv (not required on installed worker hosts)")
    workspace = ROOT / ".cache" / "worker-build" / f"{release}-{native}"
    workspace.mkdir(parents=True, exist_ok=True)
    environment = workspace / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def execute(*args: str) -> None:
        subprocess.run(
            args,
            cwd=ROOT,
            check=True,
            env={
                **os.environ,
                "PYINSTALLER_CONFIG_DIR": str(workspace / "pyinstaller-cache"),
            },
        )

    execute(
        uv, "venv", "--python", os.environ.get("GODFATHER_BUILD_PYTHON", "3.14"), str(environment)
    )
    requirements = workspace / "requirements.txt"
    execute(
        uv,
        "export",
        "--locked",
        "--package",
        "godfather-worker",
        "--no-dev",
        "--no-emit-workspace",
        "--no-hashes",
        "--output-file",
        str(requirements),
    )
    execute(
        uv,
        "pip",
        "install",
        "--python",
        str(python),
        "-r",
        str(requirements),
        f"pyinstaller=={PYINSTALLER}",
    )
    execute(
        uv,
        "pip",
        "install",
        "--python",
        str(python),
        "--no-deps",
        str(ROOT / "packages/shared-schemas"),
        str(ROOT / "packages/model-gateway"),
        str(ROOT / "packages/agent-runtime"),
        str(ROOT / "packages/worker"),
    )
    entry = workspace / "entry.py"
    entry.write_text(
        "from godfather_worker.launcher import main\nraise SystemExit(main())\n", encoding="utf-8"
    )
    execute(
        str(python),
        "-m",
        "PyInstaller",
        "--onedir",
        *(["--windowed"] if os.name == "nt" else []),
        "--collect-submodules",
        "pystray",
        "--collect-data",
        "godfather_worker",
        "--add-data",
        (
            str(ROOT / "packages/worker/src/godfather_worker/data_program.py")
            + os.pathsep
            + "godfather_worker"
        ),
        "--hidden-import",
        {
            "Windows": "keyring.backends.Windows",
            "Linux": "keyring.backends.SecretService",
            "Darwin": "keyring.backends.macOS",
        }[platform.system()],
        "--name",
        "consigliere",
        *(
            ["--icon", str(ROOT / "packages/worker/src/godfather_worker/assets/consigliere.ico")]
            if os.name == "nt"
            else []
        ),
        "--clean",
        "--noconfirm",
        "--exclude-module",
        "setuptools",
        "--exclude-module",
        "pkg_resources",
        "--exclude-module",
        "pip",
        "--exclude-module",
        "pytest",
        "--distpath",
        str(workspace / "frozen"),
        "--workpath",
        str(workspace / "build"),
        "--specpath",
        str(workspace),
        str(entry),
    )
    shutil.copytree(workspace / "frozen/consigliere", destination)
    executable = destination / ("consigliere.exe" if os.name == "nt" else "consigliere")
    # Only help: no enrollment/network/model/host grants or service installation.
    execute(str(executable), "--help")
    shutil.copyfile(ROOT / "docs/operations/worker-distribution.md", destination / "WORKERS.md")
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "version": release,
                "target": native,
                "source_revision": revision,
                "pyinstaller": PYINSTALLER,
                "status": "unsigned desktop candidate; automatic pairing and OS secret store",
                "validation": "native startup smoke; clean-host acceptance recorded separately",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (destination / "SHA256SUMS").write_text(
        "".join(
            f"{sha256(p)}  {p.relative_to(destination).as_posix()}\n"
            for p in sorted(destination.rglob("*"))
            if p.is_file()
        ),
        encoding="utf-8",
        newline="\n",
    )
    shutil.make_archive(str(destination), "zip", destination.parent, destination.name)
    Path(str(archive) + ".sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n", encoding="utf-8"
    )
    print(f"Standalone worker candidate: {archive}")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=version)
    build(parser.parse_args().version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
