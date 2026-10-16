"""Local credential-file job submission and inspection; never prints credentials."""

import argparse
import json
from pathlib import Path
from urllib.request import Request
from uuid import UUID

from godfather_contracts.jobs import JobSubmission
from godfather_worker.client import WorkerClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("submit", "list", "inspect", "cancel", "events", "attempts")
    )
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--workspace-id", type=UUID)
    parser.add_argument("--job-id", type=UUID)
    parser.add_argument("--count", type=int, default=1, choices=range(1, 101))
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--os", choices=("any", "windows", "macos", "linux"), default="any")
    args = parser.parse_args()
    document = json.loads(args.credential_file.read_text(encoding="utf-8"))
    if document.get("kind") != "admin":
        parser.error("An administrator credential file is required")
    transport = WorkerClient(args.url, document["token"])
    if args.action == "submit":
        if args.workspace_id is None:
            parser.error("--workspace-id is required for submission")
        payload = JobSubmission.model_validate(
            {
                "workspace_id": args.workspace_id,
                "requirements": {"capabilities": args.capability, "os": args.os},
            }
        )
        for _ in range(args.count):
            result = transport.post_document("/api/v1/jobs", payload)
            print(json.dumps(result))
        return 0
    path = "/api/v1/jobs?limit=200"
    if args.action != "list":
        if args.job_id is None:
            parser.error("--job-id is required")
        path = f"/api/v1/jobs/{args.job_id}"
        if args.action not in ("inspect",):
            path += "/" + args.action
    request = Request(
        transport.url + path,
        headers={"Authorization": "Bearer " + transport.token},
        method="POST" if args.action == "cancel" else "GET",
    )
    with transport.opener.open(request, timeout=10) as response:
        print(json.dumps(json.loads(response.read(8 * 1024**2)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
