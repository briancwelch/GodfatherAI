"""Local Phase 04 acceptance: 100 jobs, two native workers, restart and lease loss.

Creates synthetic records only, preserves them, and always stops/revokes its own
processes/credentials. Does not reset databases or delete application volumes.
"""

import json
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack
from datetime import datetime
from typing import Any
from urllib.request import Request
from uuid import uuid4

from godfather_contracts.jobs import JobSubmission
from godfather_worker.client import WorkerClient

from scripts.check_api_restart import compose, require_status
from scripts.check_worker_health import save_credential, stop, wait_for
from scripts.dev import ROOT


def main() -> int:
    names = compose("ps", "--format", "{{.Name}}").splitlines()
    if not names or any(not n.startswith("godfather-local-") for n in names):
        raise RuntimeError("Only the local godfather-local Compose project is permitted")
    require_status("/health/ready", 200)
    folder = ROOT / ".cache" / "phase04-runs" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    admin = save_credential(
        folder, "admin", "admin", "--email", f"scheduler-{folder.name}@example.invalid"
    )
    credentials = [admin]
    processes: list[subprocess.Popen[str]] = []
    transport = WorkerClient("http://127.0.0.1:8000", admin["token"])

    def get(path: str) -> Any:
        request = Request(
            transport.url + "/api/v1/" + path,
            headers={"Authorization": "Bearer " + transport.token},
        )
        with transport.opener.open(request, timeout=10) as response:
            return json.loads(response.read(8 * 1024**2))

    def submit(**values: object) -> dict[str, Any]:
        payload = JobSubmission.model_validate(
            {"workspace_id": workspace_id, "requirements": {"capabilities": ["coding"]}, **values}
        )
        result = transport.post_document("/api/v1/jobs", payload)
        assert isinstance(result, dict)
        return result

    try:
        workspace_id = json.loads(
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
                "Phase 04 synthetic acceptance",
            )
        )["workspace_id"]
        for name in ("LV-01", "LA-01"):
            credentials.append(
                save_credential(
                    folder, name, "worker", "--owner-id", admin["owner_id"], "--name", name
                )
            )
        jobs = [
            submit(
                input={
                    "value": f"synthetic-{n}",
                    "steps": 2,
                    "fail_until_attempt": 1 if n % 10 == 0 else 0,
                },
                retry={"limit": 1, "backoff_seconds": 0},
            )
            for n in range(100)
        ]
        incompatible = submit(requirements={"os": "linux"})
        compose("restart", "postgres")
        compose("up", "--wait", "postgres")
        compose("restart", "api")
        wait_for("API ready after actual PostgreSQL/API restarts", lambda: get_health())
        assert all(get(f"jobs/{j['id']}")["status"] == "PENDING" for j in jobs)
        print("PASS: all 100 queued jobs survived actual service restarts", flush=True)
        with ExitStack() as stack:
            for name in ("LV-01", "LA-01"):
                log = stack.enter_context((folder / f"{name}.log").open("w", encoding="utf-8"))
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "godfather_worker.cli",
                        "--credential-file",
                        str(folder / f"{name}.json"),
                        "--simulate",
                        name,
                        "--execute-synthetic",
                        "--concurrency",
                        "1",
                        "--step-seconds",
                        "0.02",
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=log,
                    text=True,
                )
                processes.append(process)

            def completed() -> bool:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("A synthetic worker exited; inspect private run logs")
                current = get("jobs?limit=200")
                ours = {j["id"]: j for j in current if j["workspace_id"] == workspace_id}
                for j in jobs:
                    if ours[j["id"]]["status"] in ("FAILED", "CANCELLED"):
                        raise RuntimeError("A workload job unexpectedly failed")
                return all(ours[j["id"]]["status"] == "COMPLETED" for j in jobs)

            wait_for(
                "100 synthetic jobs completed across two native worker processes",
                completed,
                timeout=240,
            )
            counts: Counter[str] = Counter()
            attempt_count = 0
            for job in jobs:
                attempts = get(f"jobs/{job['id']}/attempts")
                attempt_count += len(attempts)
                assert all(a["status"] in ("FAILED", "COMPLETED") for a in attempts)
                for previous, current in zip(attempts, attempts[1:], strict=False):
                    assert previous["finished_at"] is not None
                    assert datetime.fromisoformat(
                        previous["finished_at"]
                    ) <= datetime.fromisoformat(current["created_at"])
                    assert current["fencing_token"] > previous["fencing_token"]
                counts[attempts[-1]["node_id"]] += 1
            assert len(counts) == 2 and attempt_count == 110
            assert get(f"jobs/{incompatible['id']}")["status"] == "PENDING"
            print(
                "PASS: 110 durable attempts; no overlapping assignments; "
                "incompatible job remains queued",
                flush=True,
            )
            # A slower synthetic job guarantees time to observe and stop its actual worker.
            loss = submit(input={"steps": 100}, retry={"limit": 1, "backoff_seconds": 0})
            wait_for(
                "disconnect probe is RUNNING",
                lambda: get(f"jobs/{loss['id']}")["status"] == "RUNNING",
            )
            running = get(f"jobs/{loss['id']}")
            index = next(
                i
                for i, c in enumerate(credentials[1:])
                if c["credential_id"] == running["assigned_node_id"]
            )
            stop(processes[index])
            wait_for(
                "lost execution lease retried on surviving worker",
                lambda: get(f"jobs/{loss['id']}")["status"] == "COMPLETED",
                timeout=100,
            )
            recovered = get(f"jobs/{loss['id']}")
            assert recovered["attempt_count"] == 2 and recovered["fencing_token"] == 2
            attempts = get(f"jobs/{loss['id']}/attempts")
            assert attempts[0]["node_id"] != attempts[1]["node_id"]
            assert attempts[0]["error"]["code"] == "lease_expired"
            transport.opener.open(
                Request(
                    transport.url + f"/api/v1/jobs/{incompatible['id']}/cancel",
                    headers={"Authorization": "Bearer " + transport.token},
                    method="POST",
                ),
                timeout=10,
            ).close()
            result = {
                "run_id": folder.name,
                "workspace_id": workspace_id,
                "jobs_completed": 100,
                "attempts": attempt_count,
                "completed_by_node": dict(counts),
                "conflicting_assignments": 0,
                "queued_survived_actual_restarts": True,
                "disconnection_probe": recovered,
                "disconnection_attempts": attempts,
                "incompatible_job_cancelled": True,
            }
            (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        for process in processes:
            stop(process)
        for credential in reversed(credentials):
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
    print(
        f"PASS: Phase 04 local acceptance complete; evidence: {folder / 'result.json'}", flush=True
    )
    return 0


def get_health() -> bool:
    try:
        require_status("/health/ready", 200)
        return True
    except (OSError, RuntimeError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
