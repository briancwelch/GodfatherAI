"""Run repository checks or inspect prerequisites without shell-specific scripts."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS: tuple[tuple[str, ...], ...] = (
    ("uv", "run", "--locked", "--all-packages", "ruff", "format", "--check", "."),
    ("uv", "run", "--locked", "--all-packages", "ruff", "check", "."),
    ("uv", "run", "--locked", "--all-packages", "mypy"),
    ("uv", "run", "--locked", "--all-packages", "pytest"),
    ("npm", "run", "format:check"),
    ("npm", "run", "lint"),
    ("npm", "run", "typecheck"),
    ("npm", "test"),
    ("npm", "run", "build"),
)


def run_command(command: Sequence[str]) -> int:
    """Resolve Windows command shims and preserve paths containing spaces."""
    executable = shutil.which(command[0])
    if executable is None:
        print(f"Missing prerequisite: {command[0]}. See docs/operations/setup.md.", flush=True)
        return 1
    print(f"\n> {' '.join(command)}", flush=True)
    try:
        return subprocess.run([executable, *command[1:]], cwd=ROOT, check=False).returncode
    except OSError as error:
        print(f"Unable to start {command[0]}: {error}", flush=True)
        return 1


def check() -> int:
    """Stop on the first failure, retaining that command's exit status."""
    for command in CHECKS:
        if result := run_command(command):
            return result
    return 0


def doctor() -> int:
    """Read tool versions and Docker availability; never install or start services."""
    commands = (
        ("git", "--version"),
        ("uv", "--version"),
        ("node", "--version"),
        ("npm", "--version"),
        ("docker", "compose", "version"),
        ("docker", "info", "--format", "{{.OSType}}"),
    )
    failed = False
    for command in commands:
        failed = run_command(command) != 0 or failed
    print("\nPython baseline: .python-version; Node baseline: .node-version.")
    print("Docker must report linux. Version output alone does not prove compatibility.")
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "doctor"))
    args = parser.parse_args()
    return check() if args.command == "check" else doctor()


if __name__ == "__main__":
    sys.exit(main())
