# First DigitalOcean deployment: operator runbook

Release: **0.1.0-rc.5**, Linux AMD64. These are future operator commands, not
deployment authorization. This preparation creates a local commit and release
only. Do not push, transfer, connect to the Droplet or deploy during preparation.
See INSTALL.md in the archive (repository: [release guide](production-release.md)).

The operator reports Docker Engine/Compose, DNS and the production Google Web OAuth
client configured. They were not inspected remotely. Deployment root is always
`/opt/the-godfather`. Existing rc.4 images lack the founder migration and must not
be used for this first deployment.

## Private configuration

The local operator draft is `.cache/deployment-rc.5/production.env`, outside the
release and Git. Its database password is newly generated; Google credentials
must be entered privately from the configured production client. Never reuse the
development `.env`, paste secrets into chat or put credentials in command arguments.
Do not transfer the incomplete draft. Required populated fields are:

- `POSTGRES_PASSWORD`: random URL-safe value generated from at least 32 bytes.
- `GODFATHER_GOOGLE_CLIENT_ID` and `GODFATHER_GOOGLE_CLIENT_SECRET`: production Web client.
- `GODFATHER_GOOGLE_BOOTSTRAP_EMAIL`: the approved founder's exact Google address.
- `ACME_EMAIL`: monitored certificate contact.

Leave `GODFATHER_GOOGLE_BOOTSTRAP_SUBJECT` blank. No manual token extraction is
required. Use the configured callback exactly:
`https://app.the-godfather.ai/api/auth/callback`, scopes `openid email profile`.
Verify the OAuth audience/test-user settings permit the founder and invited users.

On the server the final file must be `/opt/the-godfather/production.env`, owned by
the approved operator with mode 600; its parent directory must be private. Create
or install it only after authorization, through an approved private channel/editor.
If entering it on the server, disable editor swap/backup files and shell tracing:

```bash
set +x
umask 077
test ! -e /opt/the-godfather/production.env
install -m 600 /dev/null /opt/the-godfather/production.env
vi -n /opt/the-godfather/production.env
chmod 600 /opt/the-godfather/production.env
stat -c '%U %a %n' /opt/the-godfather/production.env
```

Populate the exact keys from `production.env.example` privately. Do not run the
editor commands over an existing configuration or print the populated file.
Do not run `docker compose config` without `--quiet` when using real secrets.
Docker/root operators can inspect container environments; this is the existing
trusted-host configuration model. Back up secrets separately with encryption.

Application sessions need **no shared signing secret**: the API generates fresh
256-bit opaque session values, stores only their digests in PostgreSQL and checks
expiry/revocation on every request. Production uses an eight-hour absolute expiry,
HttpOnly/Secure/SameSite=Strict session cookies, browser-bound OIDC state/nonce/PKCE,
exact-origin mutation checks and PostgreSQL-backed authentication rate limits.
Do not invent a JWT/session secret setting. Never enable test authentication.

## Preflight and transfer, only after authorization

Resolve firewall, backup/off-host retention and restore ownership before exposure.
Permit approved SSH sources and HTTPS/certificate issuance only. Caddy alone
publishes 80/TCP, 443/TCP and 443/UDP. PostgreSQL/Redis use an internal Docker
network; API/dashboard publish no host ports. Never add a production override that
publishes 5432, 6379, 8000, 3000 or Caddy admin port 2019.

The packaged Caddyfile serves `app.the-godfather.ai` over automatically managed
HTTPS, with persistent certificate volumes and HSTS. It proxies the dashboard's
same-origin authenticated API bridge. Public direct API requests are denied;
worker paths additionally require an approved Tailscale source and machine
credentials. Remote workers remain blocked until actual tailnet routing/grants,
source preservation and onboarding are separately validated. Do not open the worker
paths to public traffic to make a test pass.

Verify the SSH host key independently and use the approved operator identity.
Replace `APPROVED_SSH_HOST` below with that operator@host; do not disable host-key
verification. From the local build host, after transfer authorization:

```powershell
$releaseName = 'godfather-0.1.0-rc.5-linux-amd64'
scp "dist/$releaseName.tar.gz" "dist/$releaseName.tar.gz.sha256" 'APPROVED_SSH_HOST:/opt/the-godfather/incoming/'
ssh APPROVED_SSH_HOST
```

On the Droplet, first inspect host capacity, existing listeners and prerequisites:

```bash
uname -sm
nproc
free -m
df -h /opt/the-godfather
timedatectl status
docker version
docker compose version
ss -lntup
test -d /opt/the-godfather/incoming
test -d /opt/the-godfather/releases
test -d /opt/the-godfather/state
test "$(stat -c %a /opt/the-godfather/production.env)" = 600
```

Verify both host/cloud firewall policies, app/API A/AAAA records, TCP reachability
for ACME and absence of conflicting listeners. Do not install or reconfigure
services during preflight without separate authorization. No cloud login is
needed to build this release.

## First install, only after authorization

Compare the archive hash with the trusted local readiness report before extraction;
the adjacent checksum file alone does not establish authenticity. Use Bash:

```bash
set -euo pipefail
umask 077
release_name=godfather-0.1.0-rc.5-linux-amd64
cd /opt/the-godfather/incoming
sha256sum -c "$release_name.tar.gz.sha256"
test ! -e "/opt/the-godfather/releases/$release_name"
tar -xzf "$release_name.tar.gz" -C /opt/the-godfather/releases
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
release_dir="/opt/the-godfather/releases/$release_name"
(cd "$release_dir" && sha256sum -c SHA256SUMS)
bash "$release_dir/scripts/install.sh" install
```

The installer loads saved images, verifies IDs/AMD64, validates configuration and
Caddy, starts private databases, explicitly applies `0007_founder_bootstrap`, then
starts healthy application/proxy services. It never clones/builds source on the
Droplet. Do not bypass a failed install or run migrations/downgrades manually.

Use the installed release to inspect status and the exact database revision:

```bash
source /opt/the-godfather/state/current/scripts/common.sh
compose ps
compose exec -T postgres psql -U godfather -d godfather -Atc 'SELECT version_num FROM alembic_version'
curl --fail --silent --show-error --head https://app.the-godfather.ai/
curl --silent --output /dev/null --write-out '%{http_code}\n' https://api.the-godfather.ai/health/ready
```

Expected head: `0007_founder_bootstrap`. The public direct API health request must
return 404. Check `docker ps`/`ss` and external port probes show no internal host
listeners. Real certificate validation must succeed; do not use `curl -k`.

Open `https://app.the-godfather.ai`, use Continue with Google with the allowlisted
account, and confirm administrator role, audit events and durable bootstrap closure.
Invite the other administrator explicitly with `platform_admin`; test uninvited
denial, private workspace/owner restrictions, logout/revocation and Secure cookies.
Never seed demonstration data or test accounts in production. FOUNDER.md in the
archive contains the detailed bootstrap procedure. Real Google/TLS checks are
pending authorized startup and cannot be certified by local fixtures.

## Rollback and failed first install

There is **no previous production release on a first install**. rc.4 cannot be a
schema-compatible fallback because it expects migration `0006_google_identity`.
If first-install migration/startup/Google acceptance fails, stop public traffic
and application writers using the attempted release (works before `state/current`
exists), and preserve all data, images, configuration and logs for diagnosis:

```bash
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
source /opt/the-godfather/releases/godfather-0.1.0-rc.5-linux-amd64/scripts/common.sh
compose stop caddy dashboard api
compose ps --all
```

Do not delete volumes, clear bootstrap state, run `down -v`, downgrade Alembic or
restart old images against a new schema. Investigate and prepare an approved fix
release. A partial install intentionally refuses a blind retry.

Before later upgrades, the installer uses the old release's quiesced paired
database/artifact backup and leaves writers stopped during migration. To make an
additional normal backup on a healthy installation:

```bash
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
bash "$GODFATHER_STATE_DIR/current/scripts/backup.sh"
```

An **image-only rollback** is permitted only when the database head exactly matches
the previous API's expected head and no intervening data/behavior incompatibility
exists. After an approved recovery decision, these commands enforce the head check
and retain all volumes. On mismatch they stop; use backup recovery instead:

```bash
set -euo pipefail
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
source "$GODFATHER_STATE_DIR/current/scripts/common.sh"
compose stop caddy dashboard api
test -L "$GODFATHER_STATE_DIR/previous"
previous_release=$(readlink -f "$GODFATHER_STATE_DIR/previous")
source "$previous_release/scripts/common.sh"
verify_release
live_head=$(compose exec -T postgres psql -U godfather -d godfather -Atc 'SELECT version_num FROM alembic_version')
expected_head=$(compose run --rm --no-deps -T --entrypoint python api -c 'from godfather_api.migrations import migration_head; print(migration_head())')
test "$live_head" = "$expected_head"
compose up -d --wait --wait-timeout 180 --pull never api dashboard caddy
ln -sfn "$previous_release" "$GODFATHER_STATE_DIR/current"
```

If an upgrade failed before updating `current`, use the last successful `current`
release instead of `previous`, under the same exact-head/data compatibility check.
Do not use this procedure to roll back the durable founder closure.

For schema/data rollback, verify the matching backup's `SHA256SUMS` and
`pg_restore --list`, retain a fresh snapshot of the failed state, and restore the
paired database/artifacts into **new empty volumes**, with the matching release
and PostgreSQL major version. Preserve artifact ownership UID/GID 10001. Use a
reviewed recovery Compose override, verify exact head, artifact reads and identity
isolation before switching traffic. This destructive recovery needs a separately
approved, concrete volume mapping; do not overwrite the existing database or
pretend that image rollback undoes a migration. The local release verifier tests
isolated database/artifact restoration; off-host encrypted recovery and actual
Droplet recovery remain acceptance gates.
