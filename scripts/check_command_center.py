"""Native workers + real browser acceptance over the local containerized API/UI.

No remote accounts, paid providers, model downloads or host services. Uses only
owned synthetic records and child processes; retains evidence and revokes credentials.
"""

import json
import shutil
import subprocess
import sys
import threading
from contextlib import ExitStack
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request
from uuid import UUID, uuid4

from godfather_contracts.agents import AgentCreate, WorkflowReport
from godfather_model_gateway import ProviderConfig
from godfather_worker.client import WorkerClient

from scripts.check_agent_runtime import WorkflowFixture
from scripts.check_api_restart import compose, require_status
from scripts.check_worker_health import save_credential, stop, wait_for
from scripts.dev import ROOT
from scripts.workflow_demo import demonstration_definition


def main() -> int:
    require_status("/health/ready", 200)
    if any(
        not n.startswith("godfather-local-")
        for n in compose("ps", "--format", "{{.Name}}").splitlines()
    ):
        raise RuntimeError("Only the local Compose project is permitted")
    node_executable = shutil.which("node")
    if node_executable is None:
        raise RuntimeError("Node.js is required for browser acceptance")
    folder = ROOT / ".cache" / "phase07-08-runs" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    credentials: list[dict[str, str]] = []
    processes: list[subprocess.Popen[str]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkflowFixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client: WorkerClient | None = None
    job_id: str | None = None
    try:
        admin = save_credential(
            folder, "admin", "admin", "--email", f"ui-{folder.name}@example.invalid"
        )
        credentials.append(admin)
        # Both owners are independent identities. LV grants this synthetic workspace.
        vegas = save_credential(
            folder, "vegas-owner", "admin", "--email", f"lv-{folder.name}@example.invalid"
        )
        credentials.append(vegas)
        primary = save_credential(
            folder,
            "primary",
            "worker",
            "--owner-id",
            vegas["owner_id"],
            "--name",
            "SIMULATED Vegas coding " + folder.name[:8],
        )
        backup = save_credential(
            folder,
            "backup",
            "worker",
            "--owner-id",
            admin["owner_id"],
            "--name",
            "SIMULATED LA backup " + folder.name[:8],
        )
        credentials.extend([primary, backup])
        workspace = json.loads(
            compose(
                "exec",
                "-T",
                "api",
                "python",
                "-m",
                "godfather_api.provision",
                "workspace",
                "--owner-id",
                admin["owner_id"],
                "--name",
                "Phase 07-08 synthetic browser acceptance",
            )
        )["workspace_id"]
        compose(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            (
                "import sys\nfrom uuid import UUID\n"
                "from godfather_api.database import Database\n"
                "from godfather_api.config import Settings\n"
                "from godfather_api.models import WorkspaceMember, Event\n"
                "d=Database(Settings())\n"
                "with d.sessions.begin() as s:\n"
                " s.add(WorkspaceMember(workspace_id=UUID(sys.argv[1]),"
                "user_id=UUID(sys.argv[2]),role='member'))\n"
                " s.add(Event(workspace_id=UUID(sys.argv[1]),actor_id=UUID(sys.argv[3]),"
                "type='workspace.synthetic_member_granted'))\n"
                "d.close()"
            ),
            workspace,
            vegas["owner_id"],
            admin["owner_id"],
        )
        config = ProviderConfig(
            id="browser-fixture", provider="ollama", url=f"http://127.0.0.1:{server.server_port}"
        )
        (folder / "providers.json").write_text(json.dumps([config.model_dump()]), encoding="utf-8")
        client = WorkerClient("http://127.0.0.1:8000", admin["token"])

        def get(path: str) -> object:
            assert client is not None
            with client.opener.open(
                Request(
                    client.url + "/api/v1/" + path,
                    headers={"Authorization": "Bearer " + client.token},
                ),
                timeout=15,
            ) as response:
                return json.loads(response.read(8 * 1024**2))

        spec = demonstration_definition(
            "phase05-fixture", "Browser recoverable coding-compatible plan"
        )
        spec.requirements.capabilities = ["coding"]
        agent = client.post_document(
            "/api/v1/agents", AgentCreate(workspace_id=UUID(workspace), definition=spec)
        )
        assert isinstance(agent, dict)
        (folder / "context.json").write_text(
            json.dumps(
                {
                    "workspace_id": workspace,
                    "primary_id": primary["credential_id"],
                    "backup_id": backup["credential_id"],
                    "agent_id": agent["id"],
                }
            ),
            encoding="utf-8",
        )
        with ExitStack() as stack:

            def launch(name: str, profile: str, pause: bool = False) -> subprocess.Popen[str]:
                log = stack.enter_context((folder / f"{name}.log").open("w", encoding="utf-8"))
                command = [
                    sys.executable,
                    "-m",
                    "godfather_worker.cli",
                    "--credential-file",
                    str(folder / f"{name}.json"),
                    "--inference-config",
                    str(folder / "providers.json"),
                    "--execute-workflows",
                    "--simulate",
                    profile,
                    "--allow-tool",
                    "plan.describe@1",
                    "--allow-tool-permission",
                    "plan.read",
                ]
                if name == "primary":
                    command += [
                        "--allow-owner",
                        admin["owner_id"],
                        "--allow-workspace",
                        workspace,
                    ]
                if pause:
                    command += ["--pause-after-checkpoint", "1"]
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log, text=True)
                processes.append(process)
                return process

            first = launch("primary", "LV-01", True)
            launch("backup", "LA-01")

            def online() -> bool:
                rows = [
                    get("nodes/" + credential["credential_id"]) for credential in (primary, backup)
                ]
                return all(isinstance(row, dict) and row["state"] == "online" for row in rows)

            def registered() -> bool:
                try:
                    return online()
                except HTTPError as error:
                    if error.code == 404:
                        return False
                    raise

            wait_for("two independently owned simulated workers online", registered)
            log = stack.enter_context((folder / "browser.log").open("w", encoding="utf-8"))
            browser = subprocess.Popen(
                [node_executable, "tests/e2e/command-center.cjs", str(folder)],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                text=True,
            )
            processes.append(browser)
            stopped = False

            def finished() -> bool:
                nonlocal stopped, job_id
                if (folder / "job.json").exists():
                    job_id = json.loads((folder / "job.json").read_text(encoding="utf-8"))["job_id"]
                if (folder / "stop-primary").exists() and not stopped:
                    stop(first)
                    stopped = True
                return browser.poll() is not None

            wait_for("browser completed failure/reassignment inspection", finished, timeout=240)
            if browser.returncode != 0:
                raise RuntimeError(f"Browser acceptance failed; inspect {folder / 'browser.log'}")
            assert job_id is not None and stopped
            details = get("command-center/jobs/" + job_id)
            assert isinstance(details, dict)
            attempts = details["attempts"]
            assert isinstance(attempts, list) and len(attempts) == 2
            # Original node starts a new process, then explicitly tries the stale attempt.
            launch("primary", "LV-01")
            wait_for("original node reconnects without changing final result", registered)
            session_id = compose(
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                (
                    "import sys\nfrom uuid import UUID\n"
                    "from godfather_api.database import Database\n"
                    "from godfather_api.config import Settings\n"
                    "from godfather_api.models import Node\n"
                    "d=Database(Settings())\ns=d.sessions()\n"
                    "print(s.get(Node,UUID(sys.argv[1])).session_id)\ns.close()\nd.close()"
                ),
                primary["credential_id"],
            ).strip()
            stale = WorkerClient("http://127.0.0.1:8000", primary["token"])
            try:
                stale.post_document(
                    f"/api/v1/workers/{primary['credential_id']}/jobs/{job_id}/workflow/report",
                    WorkflowReport(
                        session_id=UUID(session_id),
                        attempt_id=UUID(attempts[0]["id"]),
                        fencing_token=attempts[0]["fencing_token"],
                        action="step_start",
                        step_id="describe",
                        expected_checkpoint_version=1,
                    ),
                )
                raise AssertionError("Stale attempt was accepted")
            except HTTPError as error:
                assert error.code == 409
            assert get("command-center/jobs/" + job_id) == details
            (folder / "result.json").write_text(
                json.dumps(
                    {
                        "completed_at": datetime.now(UTC).isoformat(),
                        "actual_process_interruption": True,
                        "cross_owner": True,
                        "simulated_windows_to_macos": True,
                        "real_browser_submission": True,
                        "stale_reconnection_rejected": True,
                        "details": details,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
    finally:
        cleanup = []
        for process in processes:
            stop(process)
        if client and job_id:
            try:
                with client.opener.open(
                    Request(
                        client.url + f"/api/v1/jobs/{job_id}/cancel",
                        headers={"Authorization": "Bearer " + client.token},
                        method="POST",
                    ),
                    timeout=10,
                ):
                    pass
            except Exception:
                cleanup.append("job cancellation")
        for credential in reversed(credentials):
            try:
                compose(
                    "exec",
                    "-T",
                    "api",
                    "python",
                    "-m",
                    "godfather_api.provision",
                    "revoke",
                    "--credential-id",
                    credential["credential_id"],
                )
            except Exception:
                cleanup.append("credential revocation")
        server.shutdown()
        server.server_close()
        if cleanup:
            raise RuntimeError("Acceptance cleanup incomplete: " + ", ".join(cleanup))
    print(
        f"PASS: combined Phase 07-08 browser failover; evidence: {folder / 'result.json'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
