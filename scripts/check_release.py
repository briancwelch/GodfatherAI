"""Exercise saved production images on an isolated, disposable local Compose project.

Uses nonfunctional Google configuration and plain loopback HTTP. Never contacts
Google, changes the normal application database, obtains TLS certificates or uses SSH.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from scripts.dev import ROOT
from scripts.release import sha256


def docker(*args: str, data: bytes | None = None) -> bytes:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("Docker Desktop with a Linux engine is required")
    result = subprocess.run(
        [executable, *args],
        cwd=ROOT,
        input=data,
        stdout=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def verify_files(folder: Path) -> None:
    for line in (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path) != expected:
            raise RuntimeError(f"Release checksum mismatch: {relative}")


def check(folder: Path) -> None:
    verify_files(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_dirty") is not False or not re.fullmatch(
        r"[0-9a-f]{40}", manifest.get("source_revision", "")
    ):
        raise RuntimeError("Release requires clean committed source provenance")
    docker("load", "--input", str(folder / "images.tar"))
    for info in manifest["images"].values():
        actual = json.loads(docker("image", "inspect", info["tag"]))[0]
        assert actual["Id"] == info["id"]
        assert (actual["Os"], actual["Architecture"]) == ("linux", "amd64")
    api_image = manifest["images"]["api"]["tag"]
    dashboard_image = manifest["images"]["dashboard"]["tag"]
    if "build_started_utc" in manifest:
        image_config = json.loads(docker("image", "inspect", api_image))[0]["Config"]
        metadata = dict(value.split("=", 1) for value in image_config["Env"] if "=" in value)
        assert metadata["GODFATHER_RELEASE_VERSION"] == manifest["release"]
        assert metadata["GODFATHER_RELEASE_REVISION"] == manifest["source_revision"]
        assert metadata["GODFATHER_RELEASE_BUILT_AT"] == manifest["build_started_utc"]
    expected_head = (
        manifest.get("migration_head")
        or docker(
            "run",
            "--rm",
            "--network",
            "none",
            api_image,
            "python",
            "-c",
            "from godfather_api.migrations import migration_head; print(migration_head())",
        )
        .decode()
        .strip()
    )
    audit = f"""
import importlib.util, pathlib, shutil
from godfather_api.migrations import migration_head
assert migration_head() == {expected_head!r}
for module in ('pytest', 'ruff', 'mypy', 'godfather_worker'):
    assert importlib.util.find_spec(module) is None, module
for tool in ('git', 'uv'):
    assert shutil.which(tool) is None, tool
for name in ('.git', '.env', '.tools', 'tests', 'scripts', 'apps', 'packages', 'uv.lock'):
    assert not (pathlib.Path('/app') / name).exists(), name
assert not list(pathlib.Path('/app').rglob('*.pem'))
assert not list(pathlib.Path('/app').rglob('*.key'))
print('API image content and migration path passed')
"""
    print(docker("run", "--rm", "--network", "none", api_image, "python", "-c", audit).decode())
    js_audit = """
const fs=require('fs');
for (const name of ['.git','.env','.tools','tests','scripts','package-lock.json',
  'apps/dashboard/src','node_modules/typescript','node_modules/eslint']) {
  if (fs.existsSync('/app/'+name)) throw Error(name);
}
console.log('Dashboard standalone content passed');
"""
    print(
        docker("run", "--rm", "--network", "none", dashboard_image, "node", "-e", js_audit).decode()
    )
    token = uuid4().hex[:12]
    project = "godfather-release-test-" + token
    work = ROOT / ".cache" / "release-tests" / token
    work.mkdir(parents=True)
    env = work / "test.env"
    env.write_text(
        f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n"
        "GODFATHER_GOOGLE_CLIENT_ID=offline-release-test.apps.googleusercontent.com\n"
        "GODFATHER_GOOGLE_CLIENT_SECRET=offline-nonfunctional-test-value\n"
        "ACME_EMAIL=release-test@example.invalid\n",
        encoding="utf-8",
    )
    command = [
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(folder / "release.env"),
        "--env-file",
        str(env),
        "-f",
        str(folder / "compose.production.yaml"),
    ]
    config: dict[str, Any] = json.loads(
        docker(*command, "--profile", "tools", "config", "--format", "json")
    )
    services = config["services"]
    for name in ("api", "dashboard", "postgres", "redis"):
        assert not services[name].get("ports"), name
    assert config["networks"]["backend"]["internal"] is True
    assert all(not service.get("build") for service in services.values())
    assert all(service.get("platform") == "linux/amd64" for service in services.values())
    assert sum(int(services[n]["mem_limit"]) for n in services if n != "migrate") <= 2560 * 1024**2
    for kind in ("volumes", "networks"):
        for name, definition in config[kind].items():
            definition["name"] = project + "_" + name
    # The only published test port is loopback. No ACME/public listeners or DNS.
    port = free_port()
    services["caddy"]["ports"] = [
        {"target": 80, "published": str(port), "host_ip": "127.0.0.1", "protocol": "tcp"}
    ]
    caddyfile = work / "Caddyfile"
    original = (folder / "Caddyfile").read_text(encoding="utf-8")
    caddyfile.write_text(
        original.replace("app.the-godfather.ai {", "http://app.the-godfather.ai {").replace(
            "api.the-godfather.ai {", "http://api.the-godfather.ai {"
        ),
        encoding="utf-8",
    )
    for volume in services["caddy"]["volumes"]:
        if volume.get("target") == "/etc/caddy/Caddyfile":
            volume["source"] = str(caddyfile)
    local = work / "compose.json"
    local.write_text(json.dumps(config), encoding="utf-8")

    def compose(*args: str, data: bytes | None = None) -> bytes:
        return docker("compose", "--project-name", project, "-f", str(local), *args, data=data)

    try:
        # Validate the ORIGINAL production proxy configuration without starting it.
        docker(
            "run",
            "--rm",
            "--network",
            "none",
            "-e",
            "ACME_EMAIL=release-test@example.invalid",
            "--mount",
            f"type=bind,src={folder / 'Caddyfile'},dst=/etc/caddy/Caddyfile,readonly",
            manifest["images"]["caddy"]["tag"],
            "caddy",
            "validate",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        )
        for script in (folder / "scripts").glob("*.sh"):
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "bash",
                "--mount",
                f"type=bind,src={script},dst=/check.sh,readonly",
                manifest["images"]["postgres"]["tag"],
                "-n",
                "/check.sh",
            )
        compose(
            "up", "-d", "--wait", "--wait-timeout", "120", "--pull", "never", "postgres", "redis"
        )
        compose("--profile", "tools", "run", "--rm", "-T", "migrate")
        compose("--profile", "tools", "run", "--rm", "-T", "migrate")
        bootstrap = compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "godfather",
            "-d",
            "godfather",
            "-Atc",
            "SELECT version_num FROM alembic_version; "
            "SELECT id, closed_at IS NULL, founder_user_id IS NULL "
            "FROM administrator_bootstrap; "
            "SELECT count(*) FROM users; SELECT count(*) FROM google_identities;",
        )
        assert bootstrap.strip().splitlines() == [expected_head.encode(), b"1|t|t", b"0", b"0"]
        compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
            "--pull",
            "never",
            "api",
            "dashboard",
            "caddy",
        )
        for path, host, status in (
            ("/", "app.the-godfather.ai", 200),
            ("/api/control/command-center?section=nodes", "app.the-godfather.ai", 401),
            ("/api/v1/workers/register", "api.the-godfather.ai", 403),
            ("/health/ready", "api.the-godfather.ai", 404),
        ):
            request = Request(f"http://127.0.0.1:{port}{path}", headers={"Host": host})
            try:
                with urlopen(request, timeout=15) as response:
                    actual_status = response.status
            except HTTPError as error:
                actual_status = error.code
            assert actual_status == status, (path, actual_status)
        assert compose("exec", "-T", "redis", "redis-cli", "ping").strip() == b"PONG"
        compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "godfather",
            "-d",
            "godfather",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE TABLE release_probe(value text); INSERT INTO release_probe VALUES ('durable');",
        )
        compose(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from pathlib import Path; "
            "Path('/var/lib/godfather/artifacts/release-probe').write_text('durable')",
        )
        compose("stop", "caddy", "dashboard", "api")
        dump = compose(
            "exec", "-T", "postgres", "pg_dump", "-U", "godfather", "-d", "godfather", "-Fc"
        )
        (work / "database.dump").write_bytes(dump)
        compose("exec", "-T", "postgres", "createdb", "-U", "godfather", "godfather_restore_test")
        compose(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            "godfather",
            "-d",
            "godfather_restore_test",
            "--exit-on-error",
            "--no-owner",
            data=dump,
        )
        restored = compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "godfather",
            "-d",
            "godfather_restore_test",
            "-Atc",
            "SELECT value FROM release_probe",
        )
        assert restored.strip() == b"durable"
        artifact_backup = compose(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "api",
            "-c",
            "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|'); "
            "t.add('/var/lib/godfather/artifacts',arcname='artifacts'); t.close()",
        )
        (work / "artifacts.tar").write_bytes(artifact_backup)
        restore_volume = project + "_artifact_restore"
        docker("volume", "create", restore_volume)
        try:
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0",
                "-i",
                "--mount",
                f"type=volume,src={restore_volume},dst=/restore",
                api_image,
                "python",
                "-c",
                "import sys,tarfile,pathlib; "
                "t=tarfile.open(fileobj=sys.stdin.buffer,mode='r|'); "
                "t.extractall('/restore',filter='data'); "
                "assert pathlib.Path('/restore/artifacts/release-probe').read_text()=='durable'",
                data=artifact_backup,
            )
        finally:
            docker("volume", "rm", restore_volume)
        compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "120", "postgres")
        durable = compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "godfather",
            "-d",
            "godfather",
            "-Atc",
            "SELECT value FROM release_probe",
        )
        assert durable.strip() == b"durable"
        compose("up", "-d", "--wait", "--wait-timeout", "180", "api", "dashboard", "caddy")
        compose(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from godfather_api.database import Database; "
            "from godfather_api.config import Settings; assert Database(Settings()).ready()",
        )
        metrics = docker(
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            *compose("ps", "-q").decode().splitlines(),
        ).decode()
        (work / "stats.jsonl").write_text(metrics, encoding="utf-8")
        (work / "result.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "project": project,
                    "checks": [
                        "image IDs/architecture/content",
                        "production config and Caddy validation",
                        "shell syntax",
                        "fresh and repeat migrations",
                        "durable founder singleton and no seeded application identities",
                        "healthy private services",
                        "real HTTP proxy and anonymous denial",
                        "database and artifact restore",
                        "volume persistence and restart",
                    ],
                    "limitations": [
                        "Google not contacted",
                        "HTTP loopback only; no public TLS/DNS",
                        "not a Droplet load test",
                        "installer SSH flow not executed",
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Release checks passed: {work / 'result.json'}")
    finally:
        # Only the uniquely named, owned disposable test project/volumes are removed.
        compose("down", "--volumes", "--remove-orphans")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    check(parser.parse_args().directory.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
