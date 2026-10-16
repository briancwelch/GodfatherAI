"""Inspect or control local node health with an administrator credential file."""

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request
from uuid import UUID

from godfather_worker.client import WorkerClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-file", required=True, type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--node-id", type=UUID)
    parser.add_argument("--action", choices=("drain", "disable", "enable", "revoke"))
    args = parser.parse_args()
    if args.action and not args.node_id:
        parser.error("--action requires --node-id")
    try:
        credential = json.loads(args.credential_file.read_text(encoding="utf-8"))
        if credential["kind"] != "admin":
            raise ValueError("Administrator credential required")
        client = WorkerClient(args.url, credential["token"])
        route = "/api/v1/nodes" + (f"/{args.node_id}" if args.node_id else "")
        body = None
        if args.action:
            route += "/control"
            body = json.dumps({"action": args.action}).encode("utf-8")
        request = Request(
            client.url + route,
            data=body,
            headers={
                "Authorization": "Bearer " + credential["token"],
                "Content-Type": "application/json",
            },
        )
        with client.opener.open(request, timeout=10) as response:
            print(json.dumps(json.loads(response.read(4 * 1024**2)), indent=2))
    except HTTPError as error:
        parser.exit(1, f"Request refused: HTTP {error.code}\n")
    except (OSError, URLError, ValueError, KeyError, TypeError):
        parser.exit(1, "Inspection failed: check credentials, origin and coordinator readiness.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
