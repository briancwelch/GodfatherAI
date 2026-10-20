"""Isolated browser/Google-OIDC test with a real native worker and installed Ollama.

Only Google HTTP responses are mocked, exclusively inside the automated test server.
All users/jobs/permissions/telemetry use FastAPI and disposable godfather_test.
Run serially after PostgreSQL tests and the dashboard production build.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4

from godfather_contracts import Registration
from godfather_worker.client import WorkerClient
from godfather_worker.discovery import discover

from scripts.check_worker_health import stop, wait_for
from scripts.dev import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Exact already-installed local Ollama model")
    parser.add_argument(
        "--worker-executable", type=Path, help="Optional standalone worker to verify"
    )
    args = parser.parse_args()
    docker, node = shutil.which("docker"), shutil.which("node")
    if not docker or not node:
        raise RuntimeError("Existing Docker, Node and Playwright/Edge installations are required")
    for port in (8009, 3010):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Test port {port} is already in use; stop its owner explicitly")
    with urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
        models = json.load(response)["models"]
    if not any(model["name"] == args.model for model in models):
        raise RuntimeError("Requested existing local model unavailable; acceptance incomplete")
    folder = ROOT / ".cache" / "phase09-runs" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    container = "godfather-phase09-" + folder.name
    processes: list[subprocess.Popen[str]] = []
    started = False
    try:
        with ExitStack() as stack:
            docker_log = stack.enter_context((folder / "api-start.log").open("w", encoding="utf-8"))
            command = [
                docker,
                "compose",
                "--profile",
                "tools",
                "run",
                "--rm",
                "-d",
                "--name",
                container,
                "-p",
                "127.0.0.1:8009:8009",
                "-e",
                "GODFATHER_OIDC_E2E=1",
            ]
            for source, destination in (
                ("apps/api/src", "apps/api/src"),
                ("tests", "tests"),
                ("infrastructure/migrations", "infrastructure/migrations"),
            ):
                command += ["-v", f"{ROOT / source}:/app/{destination}:ro"]
            command += ["api-test", "python", "-m", "tests.e2e.auth_server"]
            subprocess.run(command, cwd=ROOT, stdout=docker_log, stderr=docker_log, check=True)
            started = True
            # Internal database-only networks intentionally suppress host port
            # forwarding. Attach only this owned test container to the existing
            # local frontend network; its published port remains loopback-only.
            subprocess.run(
                [docker, "network", "connect", "godfather-local_frontend", container],
                cwd=ROOT,
                check=True,
            )
            api_log = stack.enter_context((folder / "api.log").open("w", encoding="utf-8"))
            logs = subprocess.Popen(
                [docker, "logs", "--follow", container], stdout=api_log, stderr=api_log, text=True
            )
            processes.append(logs)

            def ready(url: str) -> bool:
                try:
                    with urlopen(url, timeout=2) as response:
                        return bool(response.status == 200)
                except (URLError, OSError):
                    return False

            wait_for(
                "isolated PostgreSQL API ready", lambda: ready("http://127.0.0.1:8009/health/ready")
            )
            env = {
                **os.environ,
                "GODFATHER_API_URL": "http://127.0.0.1:8009",
                "GODFATHER_WEB_ORIGIN": "http://127.0.0.1:3010",
            }
            ui_log = stack.enter_context((folder / "dashboard.log").open("w", encoding="utf-8"))
            ui = subprocess.Popen(
                [
                    node,
                    str(ROOT / "node_modules/next/dist/bin/next"),
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "3010",
                ],
                cwd=ROOT / "apps/dashboard",
                env=env,
                stdout=ui_log,
                stderr=ui_log,
                text=True,
            )
            processes.append(ui)
            wait_for("isolated Next.js dashboard ready", lambda: ready("http://127.0.0.1:3010"))
            browser_log = stack.enter_context((folder / "browser.log").open("w", encoding="utf-8"))
            browser = subprocess.Popen(
                [node, "tests/e2e/google-auth.cjs", str(folder), args.model],
                cwd=ROOT,
                stdout=browser_log,
                stderr=browser_log,
                text=True,
            )
            processes.append(browser)
            wait_for(
                "browser creates machine credential",
                lambda: (folder / "ready.json").exists() or browser.poll() is not None,
            )
            if browser.poll() is not None:
                raise RuntimeError("Browser authentication failed; inspect ignored browser.log")
            provider_path = folder / "providers.json"
            provider_path.write_text(
                json.dumps(
                    [{"id": "local", "provider": "ollama", "url": "http://127.0.0.1:11434"}]
                ),
                encoding="utf-8",
            )
            worker_log = stack.enter_context((folder / "worker.log").open("w", encoding="utf-8"))
            worker_command = (
                [str(args.worker_executable.resolve())]
                if args.worker_executable
                else [sys.executable, "-m", "godfather_worker.cli"]
            )
            worker = subprocess.Popen(
                [
                    *worker_command,
                    "--url",
                    "http://127.0.0.1:8009",
                    "--credential-file",
                    str(folder / "worker.json"),
                    "--inference-config",
                    str(provider_path),
                    "--execute-workflows",
                    "--allow-model-installation",
                    "--primary",
                    "research",
                ],
                cwd=ROOT,
                stdout=worker_log,
                stderr=worker_log,
                text=True,
            )
            processes.append(worker)
            deadline = monotonic() + 420
            verified = False
            while browser.poll() is None and monotonic() < deadline:
                if (folder / "revoked").exists() and not verified:
                    credentials = json.loads((folder / "worker.json").read_text(encoding="utf-8"))
                    client = WorkerClient("http://127.0.0.1:8009", credentials["token"])
                    try:
                        client.post(
                            "/api/v1/workers/register",
                            Registration(**discover().model_dump(), session_id=uuid4()),
                        )
                        raise RuntimeError("Revoked worker unexpectedly reconnected")
                    except HTTPError as error:
                        if error.code != 401:
                            raise
                    (folder / "reconnect-denied").write_text("401", encoding="ascii")
                    verified = True
                # Only live browser acceptance polls; deterministic domain tests use clocks/events.
                import threading

                threading.Event().wait(0.5)
            if browser.poll() != 0 or not verified:
                raise RuntimeError(
                    "Browser integration incomplete; inspect ignored browser.log and worker.log"
                )
            evidence = json.loads((folder / "browser-result.json").read_text(encoding="utf-8"))
            assert evidence["passed"] is True
            print(f"PASS: isolated OIDC browser + actual worker/model integration: {folder}")
            print("Real Google login remains unverified; only Google's network was mocked.")
            return 0
    finally:
        for process in reversed(processes):
            stop(process)
        if started:
            subprocess.run(
                [docker, "stop", container],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


if __name__ == "__main__":
    raise SystemExit(main())
