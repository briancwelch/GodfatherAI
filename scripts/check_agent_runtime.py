"""Phase 06 acceptance: native workflow, process interruption, checkpoint recovery.

Uses a loopback fixture by default. --ollama uses only the explicitly selected
already installed model. Synthetic records/evidence remain; owned credentials
are revoked and only owned child processes are stopped.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import threading
from collections import Counter
from contextlib import ExitStack, suppress
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request
from uuid import UUID, uuid4

from godfather_contracts.agents import (
    AgentCreate,
    WorkflowInput,
    WorkflowReport,
    WorkflowSubmission,
)
from godfather_model_gateway import ProviderConfig
from godfather_worker.client import WorkerClient

from scripts.check_api_restart import compose, require_status
from scripts.check_model_inference import FixtureProvider, available
from scripts.check_worker_health import authorize_fixture_workspace, save_credential, stop, wait_for
from scripts.dev import ROOT
from scripts.workflow_demo import demonstration_definition


class WorkflowFixture(FixtureProvider):
    def handle(self) -> None:
        # Expected when fault injection terminates this harness's own worker.
        with suppress(ConnectionResetError, BrokenPipeError):
            super().handle()

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            super().do_POST()
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = payload["messages"][-1]["content"]
        text = (
            json.dumps(
                {
                    "title": "Read-only plan",
                    "items": ["Inspect the instruction", "Prepare the summary"],
                }
            )
            if "Return only JSON matching" in prompt
            else "The validated plan was inspected and summarized safely."
        )
        self.respond(
            {
                "model": "phase05-fixture",
                "message": {"content": text},
                "done": True,
                "prompt_eval_count": 10,
                "eval_count": 12,
                "eval_duration": 100000000,
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", action="store_true")
    parser.add_argument("--model", help="Exact already-installed model identifier")
    args = parser.parse_args()
    if args.ollama and not args.model:
        parser.error("--ollama requires --model; no downloads are performed")
    require_status("/health/ready", 200)
    if any(
        not name.startswith("godfather-local-")
        for name in compose("ps", "--format", "{{.Name}}").splitlines()
    ):
        raise RuntimeError("Acceptance is restricted to the local Compose project")
    folder = ROOT / ".cache" / "phase06-runs" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    server: ThreadingHTTPServer | None = None
    credentials: list[dict[str, str]] = []
    processes: list[subprocess.Popen[str]] = []
    job_ids: list[str] = []
    admin_client: WorkerClient | None = None
    try:
        if args.ollama:
            config = ProviderConfig(
                id="workflow-acceptance", provider="ollama", timeout_seconds=180
            )
            identifier = str(args.model)
        else:
            server = ThreadingHTTPServer(("127.0.0.1", 0), WorkflowFixture)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            config = ProviderConfig(
                id="workflow-acceptance",
                provider="ollama",
                url=f"http://127.0.0.1:{server.server_port}",
            )
            identifier = "phase05-fixture"
        if not asyncio.run(available(config, identifier)):
            raise RuntimeError("Selected installed model is not available")
        (folder / "providers.json").write_text(json.dumps([config.model_dump()]), encoding="utf-8")
        admin = save_credential(
            folder, "admin", "admin", "--email", f"workflow-{folder.name}@example.invalid"
        )
        credentials.append(admin)
        worker = save_credential(
            folder,
            "worker",
            "worker",
            "--owner-id",
            admin["owner_id"],
            "--name",
            "workflow-" + folder.name,
        )
        credentials.append(worker)
        workspace_id = UUID(
            json.loads(
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
                    "Phase 06 synthetic workflow",
                )
            )["workspace_id"]
        )
        admin_client = WorkerClient("http://127.0.0.1:8000", admin["token"])
        worker_client = WorkerClient("http://127.0.0.1:8000", worker["token"])
        authorize_fixture_workspace(
            admin_client, str(workspace_id), identifier, ("plan.describe@1",)
        )

        def get(route: str) -> object:
            assert admin_client is not None
            with admin_client.opener.open(
                Request(
                    admin_client.url + "/api/v1/" + route,
                    headers={"Authorization": "Bearer " + admin_client.token},
                ),
                timeout=15,
            ) as response:
                return json.loads(response.read(1024**2))

        def workflow(job_id: str, suffix: str = "") -> dict[str, object]:
            value = get(f"workflow/jobs/{job_id}{suffix}")
            assert isinstance(value, dict)
            return value

        spec = demonstration_definition(identifier)
        agent = admin_client.post_document(
            "/api/v1/agents", AgentCreate(workspace_id=workspace_id, definition=spec)
        )
        assert isinstance(agent, dict)

        def submit() -> str:
            assert admin_client is not None
            document = admin_client.post_document(
                "/api/v1/workflow/jobs",
                WorkflowSubmission(
                    workspace_id=workspace_id,
                    agent_id=UUID(agent["id"]),
                    agent_version=1,
                    input=WorkflowInput(
                        instruction="Make a short plan for inspecting a synthetic status report."
                    ),
                ),
            )
            assert isinstance(document, dict)
            job_ids.append(str(document["id"]))
            return str(document["id"])

        def completed(job_id: str) -> bool:
            value = workflow(job_id, "/result")
            if value["status"] in ("FAILED", "CANCELLED"):
                raise RuntimeError("Workflow failed; inspect its classified execution metadata")
            return value["status"] == "COMPLETED"

        with ExitStack() as stack:

            def launch(name: str, pause: bool = False) -> subprocess.Popen[str]:
                handle = stack.enter_context((folder / f"{name}.log").open("w", encoding="utf-8"))
                command = [
                    sys.executable,
                    "-m",
                    "godfather_worker.cli",
                    "--credential-file",
                    str(folder / "worker.json"),
                    "--inference-config",
                    str(folder / "providers.json"),
                    "--execute-workflows",
                    "--simulate",
                    "LV-01",
                    "--allow-tool",
                    "plan.describe@1",
                    "--allow-tool-permission",
                    "plan.read",
                ]
                if pause:
                    command += ["--pause-after-checkpoint", "1"]
                process = subprocess.Popen(
                    command, cwd=ROOT, stdout=handle, stderr=handle, text=True
                )
                processes.append(process)
                return process

            def online() -> bool:
                rows = get("nodes")
                assert isinstance(rows, list)
                return any(
                    n["node_id"] == worker["credential_id"] and n["state"] == "online" for n in rows
                )

            normal_worker = launch("normal")
            wait_for("workflow worker registered", online)
            first = submit()
            wait_for(
                "all three normal workflow steps completed", lambda: completed(first), timeout=480
            )
            assert workflow(first)["checkpoint_version"] == 3
            normal_result = workflow(first, "/result")
            stop(normal_worker)

            def offline() -> bool:
                rows = get("nodes")
                assert isinstance(rows, list)
                return any(
                    n["node_id"] == worker["credential_id"] and n["connection_status"] == "offline"
                    for n in rows
                )

            wait_for("original worker session is offline", offline)
            interrupted_worker = launch("interrupted", True)
            wait_for("fault-injection worker registered", online)
            second = submit()
            wait_for(
                "first checkpoint committed before interruption",
                lambda: workflow(second)["checkpoint_version"] == 1,
                timeout=300,
            )
            before = workflow(second)
            job_before = before["job"]
            assert isinstance(job_before, dict)
            old_attempt = str(job_before["current_attempt_id"])
            old_fence = int(job_before["fencing_token"])
            # Capture the actual old process session without reading or printing secrets.
            # Retrieve only this run's process session using local database authority.
            old_session = compose(
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                (
                    "import sys\nfrom godfather_api.config import Settings\n"
                    "from godfather_api.database import Database\n"
                    "from godfather_api.models import Node\nfrom uuid import UUID\n"
                    "d=Database(Settings())\ns=d.sessions()\n"
                    "print(s.get(Node,UUID(sys.argv[1])).session_id)\ns.close()\nd.close()"
                ),
                worker["credential_id"],
            ).strip()
            stop(interrupted_worker)
            wait_for("stopped worker became offline", offline)

            def retry_pending() -> bool:
                value = workflow(second)["job"]
                return isinstance(value, dict) and value["status"] in ("RETRY_WAIT", "PENDING")

            wait_for("old attempt invalidated for retry", retry_pending, timeout=90)

            # Restart the actual coordinator, retaining its named artifact volume.
            compose("restart", "api")

            def ready() -> bool:
                try:
                    require_status("/health/ready", 200)
                    return True
                except Exception:
                    return False

            wait_for("API ready with durable checkpoint after restart", ready)
            assert workflow(second)["checkpoint_version"] == 1
            recovered_worker = launch("recovered")
            wait_for("replacement process registered on the same node", online)
            wait_for("workflow resumed and completed", lambda: completed(second), timeout=480)
            recovered = workflow(second)
            records = get(f"workflow/jobs/{second}/steps")
            assert isinstance(records, list)
            assert Counter(r["step_id"] for r in records) == {
                "plan": 1,
                "describe": 1,
                "summary": 1,
            }
            assert records[0]["attempt_id"] == old_attempt
            assert all(r["status"] == "COMPLETED" for r in records)
            assert recovered["checkpoint_version"] == 3
            current_job = recovered["job"]
            assert (
                isinstance(current_job, dict)
                and current_job["attempt_count"] == 2
                and current_job["fencing_token"] == old_fence + 1
            )
            checkpoints = get(f"workflow/jobs/{second}/checkpoints")
            assert isinstance(checkpoints, list) and [c["version"] for c in checkpoints] == [
                1,
                2,
                3,
            ]
            events = get(f"jobs/{second}/events")
            assert isinstance(events, list) and {
                "job.workflow.interrupted",
                "job.workflow.resumed",
                "job.workflow.completed",
            } <= {e["type"] for e in events}
            final = workflow(second, "/result")
            try:
                worker_client.post_document(
                    f"/api/v1/workers/{worker['credential_id']}/jobs/{second}/workflow/report",
                    WorkflowReport(
                        session_id=UUID(old_session),
                        attempt_id=UUID(old_attempt),
                        fencing_token=old_fence,
                        action="step_start",
                        step_id="describe",
                        expected_checkpoint_version=1,
                    ),
                )
                raise AssertionError("A stale process report was accepted")
            except HTTPError as error:
                assert error.code == 409
            assert workflow(second, "/result") == final
            assert workflow(first, "/result") == normal_result
            stop(recovered_worker)
            for path in folder.glob("*.log"):
                content = path.read_text(encoding="utf-8")
                assert "Make a short plan for inspecting" not in content
                assert all(c["token"] not in content for c in credentials)
            (folder / "result.json").write_text(
                json.dumps(
                    {
                        "completed_at": datetime.now(UTC).isoformat(),
                        "provider_mode": "real_ollama" if args.ollama else "mock_ollama",
                        "model": identifier,
                        "normal": normal_result,
                        "recovered": final,
                        "checkpoints": checkpoints,
                        "steps": records,
                        "events": events,
                        "committed_steps_repeated": False,
                        "stale_attempt_rejected": True,
                        "actual_worker_process_interrupted": True,
                        "actual_api_restart": True,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
    finally:
        cleanup_errors = []
        for process in processes:
            stop(process)
        if admin_client:
            for job_id in job_ids:
                try:
                    with admin_client.opener.open(
                        Request(
                            admin_client.url + f"/api/v1/jobs/{job_id}/cancel",
                            headers={"Authorization": "Bearer " + admin_client.token},
                            method="POST",
                        ),
                        timeout=10,
                    ):
                        pass
                except Exception:
                    cleanup_errors.append("job cancellation")
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
                cleanup_errors.append("credential revocation")
        if server:
            server.shutdown()
            server.server_close()
        if cleanup_errors:
            raise RuntimeError("Acceptance cleanup incomplete: " + ", ".join(cleanup_errors))
    print(
        f"PASS: Phase 06 workflow/process-restart acceptance; evidence: {folder / 'result.json'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
