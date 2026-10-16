"""Local Phase 03 smoke: four real processes, health isolation, and service persistence.

Uses only new synthetic owners and credentials, preserves database state for review,
and stops only the child processes it creates. Intentionally restarts local services.
"""

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.request import Request
from uuid import uuid4

from godfather_worker.client import WorkerClient

from scripts.check_api_restart import compose, require_status
from scripts.dev import ROOT

PROFILES = ("LV-01", "LV-02", "LA-01", "LA-02")


def save_credential(folder: Path, name: str, kind: str, *options: str) -> dict[str, str]:
    document: dict[str, str] = json.loads(
        compose("exec", "-T", "api", "python", "-m", "godfather_api.provision", kind, *options)
    )
    descriptor = os.open(folder / f"{name}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(document, stream)
    return document


def wait_for(description: str, condition: Callable[[], bool], timeout: int = 70) -> None:
    """Bounded live smoke polling only; unit/integration tests use deterministic clocks."""
    deadline = monotonic() + timeout
    pause = threading.Event()
    while monotonic() < deadline:
        if condition():
            print(f"PASS: {description}", flush=True)
            return
        pause.wait(0.5)
    raise RuntimeError(f"Timed out: {description}")


def stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main() -> int:
    names = compose("ps", "--format", "{{.Name}}").splitlines()
    if not names or any(not name.startswith("godfather-local-") for name in names):
        raise RuntimeError("Only the local godfather-local project is permitted")
    require_status("/health/ready", 200)
    run_id = uuid4().hex
    folder = ROOT / ".cache" / "phase03-runs" / run_id
    folder.mkdir(parents=True, mode=0o700)
    admin = save_credential(folder, "admin", "admin", "--email", f"smoke-{run_id}@example.invalid")
    credentials = {
        name: save_credential(
            folder, name, "worker", "--owner-id", admin["owner_id"], "--name", name
        )
        for name in PROFILES
    }
    transport = WorkerClient("http://127.0.0.1:8000", admin["token"])
    ids = {name: doc["credential_id"] for name, doc in credentials.items()}
    stages: list[dict[str, Any]] = []

    def nodes() -> dict[str, Any]:
        # Inspection by ID avoids an assumption about how many previous demo rows exist.
        result = {}
        for name, node_id in ids.items():
            request = Request(
                f"{transport.url}/api/v1/nodes/{node_id}",
                headers={"Authorization": "Bearer " + admin["token"]},
            )
            try:
                with transport.opener.open(request, timeout=10) as response:
                    result[name] = json.loads(response.read(65536))
            except URLError:
                return {}
        return result

    def state_is(name: str, expected: str, survivors: tuple[str, ...]) -> bool:
        current = nodes()
        if not current:
            return False
        if any(current[survivor]["state"] != "online" for survivor in survivors):
            raise RuntimeError("A surviving worker unexpectedly lost online status")
        if current[name]["state"] == expected:
            stages.append(
                {
                    "check": f"{name}-{expected}",
                    "states": {n: v["state"] for n, v in current.items()},
                }
            )
            return True
        return False

    processes: dict[str, subprocess.Popen[str]] = {}
    with ExitStack() as stack:
        try:
            for name in PROFILES:
                log = stack.enter_context((folder / f"{name}.log").open("w", encoding="utf-8"))
                processes[name] = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "godfather_worker.cli",
                        "--credential-file",
                        str(folder / f"{name}.json"),
                        "--simulate",
                        name,
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=log,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            wait_for(
                "all four worker processes registered ONLINE",
                lambda: (
                    len(current := nodes()) == 4
                    and all(v["state"] == "online" for v in current.values())
                ),
            )
            initial = nodes()
            wait_for(
                "all four persisted fresh heartbeats",
                lambda: (
                    len(current := nodes()) == 4
                    and all(
                        v["last_heartbeat_at"] != initial[n]["last_heartbeat_at"]
                        for n, v in current.items()
                    )
                ),
            )
            stop(processes["LV-01"])
            wait_for(
                "LV-01 SUSPECT while the other three remain ONLINE",
                lambda: state_is("LV-01", "suspect", ("LV-02", "LA-01", "LA-02")),
            )
            wait_for(
                "LV-01 OFFLINE while the other three remain ONLINE",
                lambda: state_is("LV-01", "offline", ("LV-02", "LA-01", "LA-02")),
            )
            before = nodes()
            compose("restart", "api")
            compose("up", "--wait", "--wait-timeout", "90", "api")
            compose("restart", "postgres")
            compose("up", "--wait", "--wait-timeout", "90", "postgres", "api")
            require_status("/health/ready", 200)
            wait_for(
                "surviving workers reconnected after API and PostgreSQL restarts",
                lambda: (
                    len(current := nodes()) == 4
                    and all(current[n]["state"] == "online" for n in ("LV-02", "LA-01", "LA-02"))
                ),
            )
            after = nodes()
            assert all(
                after[n]["node_id"] == before[n]["node_id"]
                and after[n]["owner_id"] == before[n]["owner_id"]
                and after[n]["resources"] == before[n]["resources"]
                for n in PROFILES
            )
            stages.append({"check": "service-restart-persistence", "node_ids": ids})
            print(
                "PASS: identities, ownership, credentials and telemetry survived service restarts",
                flush=True,
            )
            stop(processes["LA-01"])
            wait_for(
                "LA-01 SUSPECT while LV-02 and LA-02 remain ONLINE",
                lambda: state_is("LA-01", "suspect", ("LV-02", "LA-02")),
            )
            wait_for(
                "LA-01 OFFLINE while LV-02 and LA-02 remain ONLINE",
                lambda: state_is("LA-01", "offline", ("LV-02", "LA-02")),
            )
        finally:
            for process in processes.values():
                stop(process)
    wait_for(
        "all stopped workers independently reach OFFLINE",
        lambda: (
            len(current := nodes()) == 4 and all(v["state"] == "offline" for v in current.values())
        ),
    )
    final_nodes = nodes()
    # Revoke synthetic credentials after collecting evidence; retain rows and private files.
    for document in [*credentials.values(), admin]:
        compose(
            "exec",
            "-T",
            "api",
            "python",
            "-m",
            "godfather_api.provision",
            "revoke",
            "--credential-id",
            document["credential_id"],
        )
    report = {
        "run_id": run_id,
        "stages": stages,
        "nodes": final_nodes,
        "credentials_revoked": True,
        "result": "passed",
    }
    (folder / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS: Phase 03 smoke complete. Evidence: {folder / 'result.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
