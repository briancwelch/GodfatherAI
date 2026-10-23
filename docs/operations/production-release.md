# Local production release preparation

This guide covers Phase 10 local packaging and production configuration readiness.
The [server preparation report](server-preparation-2026-10-20.md) records the separately
authorized Docker installation and empty directories. The
[readiness checklist](production-readiness-2026-10-20.md) records the configuration
review and outstanding decisions. The operator reports DNS and the production Google OAuth client already configured;
this preparation does not recheck or change them remotely. Application deployment,
Tailscale administration and firewall changes require separate authorization.
Use [first-deployment.md](first-deployment.md) for the exact install/rollback
commands (packaged as DEPLOYMENT.md); founder instructions are packaged as FOUNDER.md.
This guide is packaged as `INSTALL.md` (linked reports are repository documents).
The release is a candidate until the acceptance gates below pass.

The current coordinator candidate is `0.1.0-rc.5`. The user has authorized review
and a local commit of the founder authentication changes, followed by a clean
release build. Review the entire proposed commit and keep all credentials excluded. Do not push or deploy without separate authorization. Build from a clean
detached worktree under the ignored `.cache/` directory to preserve development
files and avoid copying local credentials into the build context. For example:

```powershell
$sourceRevision = git rev-parse HEAD
git worktree add --detach .cache/release-source-rc.5 $sourceRevision
Set-Location .cache/release-source-rc.5
if (git status --porcelain) { throw 'Release source is dirty' }
# Use the existing build-host uv on PATH. This worktree gets its own environment.
uv run --locked --all-packages python -m scripts.release --version 0.1.0-rc.5
uv run --locked --all-packages python -m scripts.check_release dist/godfather-0.1.0-rc.5-linux-amd64
```

Do not use the Phase 09 HEAD before the release changes are committed. Run the
regression checks below before requesting commit approval; perform the final
production-image validation against the new clean release afterward. Existing
Windows development containers, `.env`, database and volumes must be preserved.

## Build and verify on Windows

Preserve the existing `.env` and `compose.yaml`. Use Docker Desktop's Linux engine
with WSL2. Builds need registry/package access; deployment loads saved images and
does not clone the source repository, build images, or install development tools.

```powershell
$env:PATH = "$PWD\.tools\bootstrap\bin;$env:PATH"
docker compose config --quiet
docker compose up --wait --wait-timeout 120
uv run --locked --all-packages python scripts/dev.py check
docker compose --profile tools build api-test
# Create the isolated godfather_test database only if it does not already exist.
docker compose exec -T postgres psql -U godfather -d postgres -Atc "SELECT datname FROM pg_database WHERE datname='godfather_test'"
docker compose exec -T postgres createdb -U godfather godfather_test
docker compose --profile tools run --rm api-test
uv run --locked --all-packages python -m scripts.release --version 0.1.0-rc.5
uv run --locked --all-packages python -m scripts.check_release dist/godfather-0.1.0-rc.5-linux-amd64
```

Skip `createdb` when the preceding query returns `godfather_test`. Integration
tests rebuild that explicitly disposable database; never point them at application
data. Run database test suites serially. Optional existing native integration:
`uv run --locked --all-packages python -m scripts.check_google_oidc --model qwen3:8b`
requires that exact model already installed and the browser test dependencies.
It mocks Google's HTTP responses, and cannot certify a real Google login.

Outputs: `dist/godfather-VERSION-linux-amd64/`, the matching `.tar.gz`, and an
external `.tar.gz.sha256`. The directory contains `images.tar` (API, dashboard,
PostgreSQL, Redis, Caddy), production Compose, Caddyfile, empty environment template,
release image tags, immutable image IDs, `images.lock.json`, manifest, SHA256SUMS, scripts, INSTALL.md
and WORKERS.md. No source checkout or populated environment is copied. Application
code necessarily exists inside the API's installed packages and Next.js output.
The API production stage excludes uv, worker, pytest, Ruff, mypy and the source
tree. The dashboard reuses Next.js standalone output. Artifacts, credentials,
Git metadata, build caches and operator files are outside the build context.

Versions are immutable: the builder refuses existing output. A failed build leaves
its partial directory for diagnosis; use a new version after fixing the failure.
The builder refuses dirty/uncommitted source before Docker work and rejects Git
changes during a build. The manifest records the exact commit, `source_dirty=false`,
image IDs and all six pinned input images. `images.lock.json` pins Python, uv, Node,
PostgreSQL, Redis and Caddy by SHA-256; release-only build arguments leave normal
development Dockerfile defaults unchanged. Application dependencies use `uv.lock`
and `package-lock.json`. Root `pyproject.toml` also constrains all seven isolated
Hatchling build dependencies by version/hash, with those constraints recorded in
`uv.lock`; no application dependency version changed. Hash enforcement uses the
pinned uv release's experimental build-dependency-hashes support, validated by the
release checks. See [uv build constraints](https://docs.astral.sh/uv/reference/settings/#build-constraint-dependencies).
Rebuilds use those recorded inputs; archive timestamps and
build metadata may still differ, so byte-identical output is not promised. The
delivered archive, internal checksums and loaded image IDs must all be verified.

## Server prerequisites and operator decisions

Target: existing Ubuntu 24.04 LTS, AMD64, 2 vCPUs, 4GB RAM, 120GB disk. Docker and
directories were verified in the server preparation report; they were not rechecked
remotely during configuration readiness. Before deployment recheck OS/architecture, existing
services/port conflicts, storage, time synchronization, SSH host key/access, Docker
Engine and Compose v2.20+ (including `up --wait` and multiple `--env-file` support),
least-privilege Tailscale connectivity/grants and firewall policy. Docker group
membership is root-equivalent. Scripts install none of these prerequisites.

Use a dedicated operator with reviewed Docker access. Allow SSH only from approved
administration sources, 80/TCP and 443/TCP for HTTPS/certificate issuance, optionally
443/UDP for HTTP/3, and only approved Tailscale traffic. Do not publish 5432, 6379,
8000, 3000 or 2019. Cloud and host firewall rules need separate authorization;
Docker's published ports require Docker-aware firewall review.

Service RAM ceilings: PostgreSQL 1024MiB, API 768MiB, dashboard 512MiB, Caddy 128MiB,
Redis 128MiB: **2560MiB total**. Migrations use up to 768MiB while the API is stopped.
One API process uses a pool of at most ten connections; PostgreSQL allows 40.
Redis is transient with a 64MiB eviction budget, not an authoritative job store.
No inference models or worker processes run on the coordinator. CPU quotas are
ceilings, not reservations; contention on two vCPUs is possible. Image builds stay
on the development machine. Allow at least 15GiB free for initial images/backups,
then monitor artifact/database growth, disk/inodes, OOM events, latency and swap.
120GB capacity and these limits are an initial configuration, not a capacity test
or a workload guarantee. Log rotation is 3 x 10MiB per container. Configure backup
retention/off-host storage before growth consumes the volume.

## Required secrets, identities and DNS (prepare locally; apply only after approval)

Keep `/opt/the-godfather/production.env` outside release directories, owned by the
operator with mode 600. Fill the supplied template privately:

| Setting                            | Required value                                                |
| ---------------------------------- | ------------------------------------------------------------- |
| POSTGRES_PASSWORD                  | Unique random URL-safe password, at least 32 random bytes     |
| GODFATHER_GOOGLE_CLIENT_ID         | Production Google Web OAuth client ID                         |
| GODFATHER_GOOGLE_CLIENT_SECRET     | Client secret, only injected into API/migrate                 |
| GODFATHER_GOOGLE_BOOTSTRAP_EMAIL   | Exact founder email, verified during normal Google OIDC login |
| GODFATHER_GOOGLE_BOOTSTRAP_SUBJECT | Optional legacy additional subject pin; normally blank        |
| ACME_EMAIL                         | Operator certificate contact                                  |

Register exact OAuth callback
`https://app.the-godfather.ai/api/auth/callback`, scopes `openid email profile`.
The operator reports Google client setup complete. Confirm the configured callback,
audience and credentials privately; the founder allowlist, invitations and real
account acceptance remain deployment prerequisites. Existing UUIDs must be linked explicitly through
`python -m godfather_api.identity`; consult `docs/history/phases.md#phase-09` in the
development checkout before migration. The [one-time founder flow](founder-bootstrap.md)
requires a signed, server-verified Google identity with `email_verified=true`; it
does not require manually extracting a subject or ID token. Migration
`0007_founder_bootstrap` persists permanent closure after successful bootstrap and
closes existing installations with administrators or Google identities. This change
is included in rc.5; historical rc.4 does not contain it. Remove
bootstrap values after activation as configuration hygiene. Invite
the second administrator with equal role; there is no hardcoded account count.

The operator reports DNS configured. At authorized deployment, verify public A records for `app.the-godfather.ai` and
`api.the-godfather.ai` point to the approved Droplet IPv4; add AAAA only after IPv6
is configured and tested. Caddy manages HTTPS and persists certificate material in
private Docker volumes. Apex DNS/redirect is optional and absent from this release.
Workers must resolve `api.the-godfather.ai` to the Droplet's **Tailscale address**
using approved split DNS or an explicit host mapping while retaining that HTTPS
hostname for certificate validation. Ordinary public routing is intentionally
denied for worker paths. Tailscale grants must restrict actual owners/devices;
the proxy's tailnet CIDR check supplements, and never replaces, machine auth.
Verify client source-address preservation on the actual Ubuntu Docker host.

Secrets are injected at runtime, never baked into images. Compose environment
values are visible to host root/Docker operators. This initial release uses a
mode-600 environment file, not an external vault; confirm this trust model before
deployment. Back up it and TLS secrets separately with encryption/access controls.
Changing POSTGRES_PASSWORD in the file does not rotate an existing database role:
perform coordinated role rotation during reviewed maintenance, then update config.

## SSH deployment workflow (instructions only; not executed)

After remote authorization, verify the SSH host fingerprint out of band. Copy only
the archive and checksum with normal OpenSSH. Do not disable host-key verification.
Keep production secrets out of shell history and transfer them separately.

```powershell
scp dist/godfather-0.1.0-rc.5-linux-amd64.tar.gz dist/godfather-0.1.0-rc.5-linux-amd64.tar.gz.sha256 operator@DROPLET:/opt/the-godfather/incoming/
ssh operator@DROPLET
```

The base directories and private environment file must already be prepared by the
authorized operator. On the Droplet, use the received checksum only after comparing
it to the trusted local hash; a checksum transferred beside an archive isn't a
signature or an independent authenticity guarantee.

```bash
cd /opt/the-godfather/incoming
sha256sum -c godfather-0.1.0-rc.5-linux-amd64.tar.gz.sha256
tar -xzf godfather-0.1.0-rc.5-linux-amd64.tar.gz -C /opt/the-godfather/releases
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
bash /opt/the-godfather/releases/godfather-0.1.0-rc.5-linux-amd64/scripts/install.sh install
```

The installer checks RAM/disk/platform, configuration/checksums, saved image IDs,
and Caddy validity; loads images; starts only private dependencies; applies explicit
Alembic upgrade; then starts healthy API, dashboard and proxy. No source clone,
server-side build or service installation occurs. Initial install refuses existing
project containers/database volumes to avoid accidental adoption. Inspect partial
installations manually before retrying. The stable Compose project and volume names
are `godfather-production_*`, independent of release version/directory.

For upgrades, transfer/extract a new immutable version and run its `install.sh upgrade`.
The old release takes a quiesced backup; all application/proxy containers remain
stopped through migration. Database image changes are refused pending a separate
review (including PostgreSQL major-version migration). Any failed migration stops
installation before application startup. Any startup failure requires explicit
operator recovery; there is no blind downgrade. `state/current` and `state/previous`
track successfully installed releases; retain both packages/images. Maintenance
interrupts requests and permits worker leases to expire; portable jobs resume under
existing fencing/retry rules. Communicate maintenance and drain work as appropriate.

## Backup, restore and rollback

```bash
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
bash "$GODFATHER_STATE_DIR/current/scripts/backup.sh"
```

Backup pauses API/scheduler/dashboard/proxy, dumps PostgreSQL in custom format,
archives artifacts, validates dump/archive readability and writes SHA256SUMS and
release metadata under `state/backups/UTC-PID`. It restores running services after
a normal backup, but an upgrade's backup leaves them stopped. Workers cannot commit
while the snapshot is taken; no unreplicated GPU/host state is promised. Backups
are confidential application data, not release artifacts. Schedule daily and
pre-upgrade backups, copy encrypted backups off-host, select retention/recovery
objectives and test recovery. No cron, cloud backup or off-host transfer is installed.

Restore is deliberately manual and destructive; requires a separately approved
maintenance/recovery decision. Verify backup SHA256SUMS, stop all app/proxy services,
retain a new current-state backup, and select the matching old release. Keep
PostgreSQL major version unchanged. Use its `pg_restore --list` first, then restore
the dump into a **new empty database/volume**, and extract the paired artifact
archive into a **new artifact volume**, preserving UID/GID 10001. Never overlay a
partial artifact store or drop existing production data as an automatic rollback.
Use a reviewed Compose recovery override to attach these restored volumes; start
the matching release without migrating forward, verify exact Alembic head and
authorized artifact reads, then switch traffic/current pointer after acceptance.
Retain old volumes for investigation. A schema-compatible image-only rollback can
use the previous images only when readiness matches their exact migration head;
otherwise use the matching backup. Never run `down -v` against production.

## Deployment and operational acceptance gates

Before exposure, complete host/cloud firewall, private secrets, security review and
backup/recovery policy. At authorized startup, validate real Google login/PKCE
callback and logout/revocation on HTTPS; two equal admins;
invitation-only denial; private workspace/owner isolation; production secret rotation;
actual TLS/DNS and tailnet routing/grants; single-use worker enrollment implementation;
signed native worker distribution; real remote macOS execution and disconnect/fencing;
backup restore on a separate environment; dependency/security review and audit
retention; measured load/memory on the 4GB Droplet. Local fixture tests and loopback
HTTP proxy tests are explicitly insufficient for these external gates.

References: [Docker production Compose](https://docs.docker.com/compose/how-tos/production/),
[uv container installs](https://docs.astral.sh/uv/guides/integration/docker/),
[Next.js standalone output](https://nextjs.org/docs/app/api-reference/config/next-config-js/output),
[Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
