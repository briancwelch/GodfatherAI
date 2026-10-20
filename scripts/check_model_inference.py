"""Local Phase 05 native-worker acceptance; mock provider by default, real Ollama opt-in.

Creates only synthetic records, stops its own processes/server and revokes its own
credentials. Does not install software, download models or contact remote providers.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import threading
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request
from uuid import uuid4

from godfather_contracts.jobs import InferenceSubmission
from godfather_model_gateway import ProviderConfig
from godfather_model_gateway.providers import create_provider
from godfather_worker.client import WorkerClient

from scripts.check_api_restart import compose, require_status
from scripts.check_worker_health import authorize_fixture_workspace, save_credential, stop, wait_for
from scripts.dev import ROOT


class FixtureProvider(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        pass  # No prompt/URL/access logging.

    def respond(self, data: object) -> None:
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/api/tags":
            self.respond(
                {"models": [{"name": "phase05-fixture", "digest": "fixture-v1", "size": 1}]}
            )
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            self.respond(
                {"capabilities": ["completion"], "model_info": {"fixture.context_length": 4096}}
            )
        elif self.path == "/api/chat":
            final = {
                "model": "phase05-fixture",
                "message": {"content": "fixture response"},
                "done": True,
                "prompt_eval_count": 4,
                "eval_count": 2,
                "eval_duration": 100000000,
            }
            if not data["stream"]:
                self.respond(final)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Connection", "close")
            self.end_headers()
            first = {"model": "phase05-fixture", "message": {"content": "fixture "}, "done": False}
            final["message"] = {"content": "response"}
            self.wfile.write((json.dumps(first) + "\n").encode())
            self.wfile.flush()
            self.wfile.write((json.dumps(final) + "\n").encode())
            self.wfile.flush()
            self.close_connection = True
        else:
            self.send_error(404)


async def available(config: ProviderConfig, identifier: str) -> bool:
    provider = create_provider(config)
    try:
        return any(
            m.identifier == identifier and "stream" in m.operations
            for m in await provider.discover()
        )
    finally:
        await provider.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", action="store_true", help="Use already-running loopback Ollama")
    parser.add_argument("--model", help="Exact installed model identifier, required with --ollama")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=32,
        help="Output budget for the installed model, including reasoning tokens",
    )
    parser.add_argument(
        "--verify-restart",
        action="store_true",
        help="Restart the local API and verify the completed results remain durable",
    )
    args = parser.parse_args()
    if args.ollama and not args.model:
        parser.error("--ollama requires an exact already-installed --model")
    if not 1 <= args.max_tokens <= 8192:
        parser.error("--max-tokens must be between 1 and 8192")
    require_status("/health/ready", 200)
    folder = ROOT / ".cache" / "phase05-runs" / uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    server: ThreadingHTTPServer | None = None
    process: subprocess.Popen[str] | None = None
    credentials: list[dict[str, str]] = []
    job_ids: list[str] = []
    client: WorkerClient | None = None
    try:
        if args.ollama:
            config = ProviderConfig(id="acceptance", provider="ollama")
            identifier = str(args.model)
        else:
            server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureProvider)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            config = ProviderConfig(
                id="acceptance", provider="ollama", url=f"http://127.0.0.1:{server.server_port}"
            )
            identifier = "phase05-fixture"
        if not asyncio.run(available(config, identifier)):
            raise RuntimeError("The exact installed model does not advertise streaming chat")
        config_path = folder / "providers.json"
        with config_path.open("x", encoding="utf-8") as handle:
            json.dump([config.model_dump()], handle)
        admin = save_credential(
            folder, "admin", "admin", "--email", f"inference-{folder.name}@example.invalid"
        )
        credentials.append(admin)
        worker = save_credential(
            folder,
            "worker",
            "worker",
            "--owner-id",
            admin["owner_id"],
            "--name",
            "inference-" + folder.name,
        )
        credentials.append(worker)
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
                "Synthetic inference acceptance",
            )
        )["workspace_id"]
        client = WorkerClient("http://127.0.0.1:8000", admin["token"])
        authorize_fixture_workspace(client, workspace_id, identifier)

        def get(path: str) -> object:
            assert client is not None
            with client.opener.open(
                Request(
                    client.url + "/api/v1/" + path,
                    headers={"Authorization": "Bearer " + client.token},
                ),
                timeout=40,
            ) as response:
                return json.loads(response.read(1024**2))

        with ExitStack() as stack:
            log_path = folder / "worker.log"
            log = stack.enter_context(log_path.open("w", encoding="utf-8"))
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "godfather_worker.cli",
                    "--credential-file",
                    str(folder / "worker.json"),
                    "--inference-config",
                    str(config_path),
                    "--simulate",
                    "LV-01",
                ],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                text=True,
            )

            def registered() -> bool:
                if process is not None and process.poll() is not None:
                    raise RuntimeError("Inference worker exited; inspect its private log")
                models = get("models?workspace_id=" + workspace_id)
                assert isinstance(models, list)
                return any(
                    m["available"] and m["deployment"]["identifier"] == identifier for m in models
                )

            wait_for("native worker advertised installed model", registered)
            results: list[object] = []
            for streaming in (True, False):
                payload = InferenceSubmission.model_validate(
                    {
                        "workspace_id": workspace_id,
                        "requirements": {
                            "model_selection": {"identifier": identifier, "stream": streaming}
                        },
                        "input": {
                            "prompt": "Reply with one short greeting.",
                            "stream": streaming,
                            "parameters": {"max_tokens": args.max_tokens},
                        },
                        "timeout_seconds": 120,
                    }
                )
                document = client.post_document("/api/v1/inference/jobs", payload)
                assert isinstance(document, dict)
                job_id = str(document["id"])
                job_ids.append(job_id)
                sse_path = folder / f"{job_id}.sse"
                seen_snapshot = False

                def read_stream(current_job: str = job_id, destination: Path = sse_path) -> None:
                    nonlocal seen_snapshot
                    assert client is not None
                    with client.opener.open(
                        Request(
                            client.url + f"/api/v1/inference/jobs/{current_job}/stream",
                            headers={"Authorization": "Bearer " + client.token},
                        ),
                        timeout=40,
                    ) as response:
                        raw = response.read(1024**2).decode()
                    with destination.open("a", encoding="utf-8") as handle:
                        handle.write(raw)
                    seen_snapshot = seen_snapshot or "event: snapshot" in raw

                read_stream()

                def finished(current_job: str = job_id) -> bool:
                    value = get(f"inference/jobs/{current_job}/result")
                    assert isinstance(value, dict)
                    if value["status"] in ("FAILED", "CANCELLED"):
                        raise RuntimeError("Inference failed; inspect classified attempt metadata")
                    return bool(value["status"] == "COMPLETED")

                wait_for("inference completed through gateway", finished, timeout=150)
                if not seen_snapshot:
                    read_stream()
                value = get(f"inference/jobs/{job_id}/result")
                assert (
                    isinstance(value, dict) and value["text"] and value["valid"] and seen_snapshot
                )
                assert value["metadata"]["deployment"]["identifier"] == identifier
                results.append(value)
            if args.verify_restart:
                compose("restart", "api")

                def ready_again() -> bool:
                    try:
                        require_status("/health/ready", 200)
                        return True
                    except Exception:
                        return False

                wait_for("API ready after actual restart", ready_again)
                assert [get(f"inference/jobs/{job_id}/result") for job_id in job_ids] == results
                print("PASS: completed inference results survived actual API restart", flush=True)
            stop(process)
            log_text = log_path.read_text(encoding="utf-8")
            assert "Reply with one short greeting." not in log_text
            assert all(c["token"] not in log_text for c in credentials)
            (folder / "result.json").write_text(
                json.dumps(
                    {
                        "provider_mode": "real_ollama" if args.ollama else "mock_ollama",
                        "model": identifier,
                        "streaming_and_nonstreaming": True,
                        "native_worker_process": True,
                        "durable_after_api_restart": args.verify_restart,
                        "results": results,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
    finally:
        cleanup_errors: list[str] = []
        if process is not None:
            stop(process)
        if client is not None:
            for job_id in job_ids:
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
        if server is not None:
            server.shutdown()
            server.server_close()
        if cleanup_errors:
            raise RuntimeError("Acceptance cleanup incomplete: " + ", ".join(cleanup_errors))
    print(
        f"PASS: Phase 05 {'real Ollama' if args.ollama else 'mock provider'} acceptance; "
        f"evidence: {folder / 'result.json'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
