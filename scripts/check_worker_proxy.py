"""Exercise the release Caddy routes on loopback with a synthetic HTTP backend."""

import json
import socket
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from scripts.check_worker_health import wait_for
from scripts.dev import ROOT


def main() -> int:
    suffix = uuid4().hex[:12]
    network, backend, proxy = (
        f"godfather-proxy-{suffix}-{part}" for part in ("net", "api", "edge")
    )

    def command(*args: str) -> str:
        return subprocess.run(
            ["docker", *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with TemporaryDirectory(prefix="godfather-proxy-") as temporary:
        folder = Path(temporary)
        (folder / "backend.py").write_text("""import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        trusted = self.headers.get("X-Godfather-Proxy-Token") == "synthetic-test-proxy"
        peer = self.headers.get("X-Godfather-Peer")
        body = json.dumps({"trusted": trusted, "peer": peer}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)
    do_POST = do_GET
    def log_message(self, *args): pass
HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
""")
        (folder / "manifest.json").write_text('{"artifacts": []}')
        command("network", "create", network)
        try:
            command(
                "run",
                "-d",
                "--name",
                backend,
                "--network",
                network,
                "--network-alias",
                "api",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "-v",
                f"{folder}:/test:ro",
                "--entrypoint",
                "python",
                "godfather/api:0.2.0-rc.5",
                "/test/backend.py",
            )
            command(
                "run",
                "-d",
                "--name",
                proxy,
                "--network",
                network,
                "-p",
                f"127.0.0.1:{port}:80",
                "-e",
                "GODFATHER_PUBLIC_HOSTS=http://127.0.0.1:80",
                "-e",
                "GODFATHER_APP_HOST=browser.example.invalid",
                "-e",
                "ACME_EMAIL=test@example.invalid",
                "-e",
                "GODFATHER_PROXY_TOKEN=synthetic-test-proxy",
                "-v",
                f"{ROOT / 'infrastructure/release/Caddyfile'}:/etc/caddy/Caddyfile:ro",
                "-v",
                f"{folder}:/srv/godfather-downloads:ro",
                "godfather/caddy:0.2.0-rc.5",
            )
            origin = f"http://127.0.0.1:{port}"

            def ready() -> bool:
                try:
                    with urlopen(origin + "/api/v1/workers/register", timeout=2) as response:
                        return bool(response.status == 200)
                except (URLError, OSError):
                    return False

            wait_for("loopback Caddy routing", ready)
            request = Request(
                origin + "/api/v1/workers/register",
                data=b"{}",
                headers={"X-Godfather-Peer": "192.0.2.123", "X-Godfather-Proxy-Token": "forged"},
            )
            with urlopen(request, timeout=5) as response:
                result = json.load(response)
            assert result["trusted"] and result["peer"] != "192.0.2.123"
            for path in (
                "/api/v1/administration/users",
                "/api/v1/nodes",
                "/api/v1/provider-connections",
                "/health/ready",
                "/downloads/production.env",
            ):
                try:
                    urlopen(origin + path, timeout=5).close()
                except HTTPError as error:
                    assert error.code == 404
                else:
                    raise AssertionError("Private route exposed: " + path)
            with urlopen(origin + "/downloads/manifest.json", timeout=5) as response:
                assert json.load(response) == {"artifacts": []}
            print(
                "Passed Caddy routing, private-route isolation, downloads and spoofed headers. "
                "Backend authentication is covered separately by PostgreSQL tests."
            )
        finally:
            subprocess.run(["docker", "rm", "-f", proxy, backend], capture_output=True, check=False)
            subprocess.run(["docker", "network", "rm", network], capture_output=True, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
