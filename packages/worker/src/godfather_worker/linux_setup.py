"""In-place per-user Linux portable worker upgrade, retaining external owner data."""

import json
import subprocess
import sys
from pathlib import Path

from godfather_worker.app_installation import contained_directory, replace_payload
from godfather_worker.native_desktop import acquire_lock, data_folder
from godfather_worker.updates import native_target, wait_for_previous


def main() -> int:
    wait_for_previous()
    source = Path(sys.executable).resolve().parent
    destination = Path(sys.argv[sys.argv.index("--install-update") + 1]).resolve()
    contained_directory(destination, destination.parent)
    for folder in (source, destination):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("target") != native_target() or not (folder / "consigliere").is_file():
            raise ValueError("Unrecognized portable worker installation")
    lock = acquire_lock(data_folder())
    if lock is None:
        raise OSError("Worker still running; installation was not changed")
    try:
        replace_payload(source, destination)
        executable = destination / "consigliere"
        executable.chmod(0o700)
        subprocess.Popen([str(executable)])
    finally:
        lock.close()
    return 0
