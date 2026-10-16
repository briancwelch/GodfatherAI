"""Verify the local Phase 02 API across API/database restart and a database outage."""

from __future__ import annotations

import shutil
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from scripts.dev import ROOT


def compose(*args: str) -> str:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("Docker is required; see docs/operations/setup.md")
    result = subprocess.run(
        [executable, "compose", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sql(statement: str) -> str:
    return compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "godfather",
        "-d",
        "godfather",
        "-v",
        "ON_ERROR_STOP=1",
        "-Atc",
        statement,
    )


def status(path: str) -> int:
    try:
        with urlopen(f"http://127.0.0.1:8000{path}", timeout=15) as response:
            return int(response.status)
    except HTTPError as error:
        return error.code


def require_status(path: str, expected: int) -> None:
    actual = status(path)
    if actual != expected:
        raise RuntimeError(f"{path}: expected HTTP {expected}, received {actual}")


def main() -> int:
    names = compose("ps", "--format", "{{.Name}}").splitlines()
    if not names or any(not name.startswith("godfather-local-") for name in names):
        raise RuntimeError("This probe is restricted to the godfather-local development project")
    table = f"phase02_restart_probe_{uuid4().hex}"
    sql(f"CREATE TABLE {table} (value text NOT NULL); INSERT INTO {table} VALUES ('durable')")
    try:
        compose("restart", "api")
        compose("up", "--wait", "--wait-timeout", "90", "api")
        require_status("/health/ready", 200)
        if sql(f"SELECT value FROM {table}") != "durable":
            raise RuntimeError("Committed probe did not survive API restart")
        compose("restart", "postgres")
        compose("up", "--wait", "--wait-timeout", "90", "postgres", "api")
        require_status("/health/ready", 200)
        if sql(f"SELECT value FROM {table}") != "durable":
            raise RuntimeError("Committed probe did not survive database restart")
        try:
            compose("stop", "postgres")
            require_status("/health/live", 200)
            require_status("/health/ready", 503)
        finally:
            compose("up", "--wait", "--wait-timeout", "90", "postgres")
        compose("up", "--wait", "--wait-timeout", "90", "api")
        require_status("/health/ready", 200)
    finally:
        sql(f"DROP TABLE {table}")
    print("PASS: API restart, PostgreSQL restart, durable data, outage 200/503, and recovery.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
