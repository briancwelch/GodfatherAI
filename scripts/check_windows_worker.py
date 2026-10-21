"""Native installer/startup and isolated Windows Credential Manager smoke."""

import argparse
import json
import platform
import subprocess
from pathlib import Path
from uuid import uuid4

from godfather_worker import native_desktop

from scripts.release import sha256


def check(setup: Path) -> dict[str, str]:
    if platform.system() != "Windows":
        raise RuntimeError("Native Windows host required")
    digest = sha256(setup)
    if Path(str(setup) + ".sha256").read_text().strip() != f"{digest}  {setup.name}":
        raise RuntimeError("Installer checksum mismatch")
    manifest = json.loads(Path(str(setup) + ".manifest.json").read_text())
    # Install only into the setup executable's own temporary test directory.
    subprocess.run([str(setup.resolve()), "--self-test"], check=True, timeout=120)
    original_service = native_desktop.SERVICE
    native_desktop.SERVICE = "ai.the-godfather.synthetic-smoke." + uuid4().hex
    store = native_desktop.CredentialStore()
    try:
        assert store.read() is None
        store.write("synthetic smoke value; no real credential")
        assert store.read() == "synthetic smoke value; no real credential"
        store.delete()
        assert store.read() is None
    finally:
        try:
            store.delete()
        finally:
            native_desktop.SERVICE = original_service
    return {
        "version": manifest["version"],
        "source_revision": manifest["source_revision"],
        "sha256": digest,
        "result": "Temporary install/repeat, packaged Tk/tray and isolated OS-store checks passed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = check(args.setup)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(report["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
