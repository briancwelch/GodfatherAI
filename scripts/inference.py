"""Explicit local inference client; credentials are read from ignored private files."""

import argparse
import json
from pathlib import Path
from urllib.request import Request

from godfather_contracts.jobs import InferenceSubmission
from godfather_worker.client import WorkerClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("models", "submit", "result", "stream", "cancel", "metrics")
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--workspace-id")
    parser.add_argument("--job-id")
    parser.add_argument(
        "--request-file",
        type=Path,
        help="Private JSON InferenceSubmission file; avoids prompts in process arguments",
    )
    args = parser.parse_args()
    credential = json.loads(args.credential_file.read_text(encoding="utf-8"))
    if credential.get("kind") != "admin":
        parser.error("An administrator credential is required")
    client = WorkerClient(args.url, credential["token"])
    if args.action == "submit":
        if args.request_file is None:
            parser.error("submit requires --request-file")
        payload = InferenceSubmission.model_validate_json(
            args.request_file.read_text(encoding="utf-8")
        )
        value = client.post_document("/api/v1/inference/jobs", payload)
        assert isinstance(value, dict)
        # The normal submit output contains identities/status only, not the private prompt.
        print(json.dumps({key: value[key] for key in ("id", "status", "workspace_id")}))
        return 0
    if args.action in ("models", "metrics"):
        from uuid import UUID

        if args.workspace_id is None:
            parser.error("This action requires --workspace-id")
        workspace_id = str(UUID(args.workspace_id))
        path = (
            "models" if args.action == "models" else "inference/metrics"
        ) + f"?workspace_id={workspace_id}"
    else:
        from uuid import UUID

        if args.job_id is None:
            parser.error("This action requires --job-id")
        job_id = str(UUID(args.job_id))
        path = (
            f"jobs/{job_id}/cancel"
            if args.action == "cancel"
            else f"inference/jobs/{job_id}/{args.action}"
        )
    request = Request(
        client.url + "/api/v1/" + path,
        headers={"Authorization": "Bearer " + client.token},
        method="POST" if args.action == "cancel" else "GET",
    )
    with client.opener.open(request, timeout=40) as response:
        if args.action == "stream":
            # SSE snapshots replace text, never append snapshots across attempts.
            for line in response:
                print(line.decode("utf-8").rstrip(), flush=True)
        else:
            print(json.dumps(json.loads(response.read(1024**2)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
