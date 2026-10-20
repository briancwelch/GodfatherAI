# Production configuration and deployment readiness - 2026-10-20

Current preparation: the operator reports DNS and Google OAuth configured. The
user has authorized local review/commit of founder authentication and a clean
`0.1.0-rc.5` build, secure local configuration, image/migration/checksum validation
and exact install/rollback instructions. No push, transfer, SSH or deployment is
authorized. See [first-deployment.md](first-deployment.md); the final release report
in ignored `dist/` records executed checks and remaining blockers.

Historical readiness snapshot: the manual first-founder subject-verification
instructions below are superseded by the [one-time founder setup](founder-bootstrap.md)
in the current source. It requires a new release containing migration
`0007_founder_bootstrap`; existing rc.4 artifacts remain unchanged.

**Configuration review complete; deployment is blocked by the open gates below.**
This milestone authorizes local preparation only. No SSH connection, production
environment file, secret generation, artifact transfer, application startup, DNS,
OAuth, firewall or Tailscale change was performed. No real integration was replaced
with simulated data. The Droplet facts below come from the
[server preparation report](server-preparation-2026-10-20.md), not a fresh host check.

## Readiness checklist

| State                         | Requirement / exact next operator action                                                                                                                              |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Complete locally              | Active release guide and script examples use `/opt/the-godfather`; blank template documents all inputs. Historical reports and immutable rc.3 archives are preserved. |
| Complete locally              | Compose topology and Caddy syntax checked; only Caddy publishes ports. Secret-file ignore rules added. See validation below.                                          |
| Prepared, not applied         | DNS, Google Web client, first-admin bootstrap, firewall rules and secret installation procedures below.                                                               |
| Decision required             | Confirm Droplet IPv4, domain control, DNS provider, approved SSH source CIDRs and SSH operator identity/recovery access.                                              |
| Manual configuration required | Create production Google client; select audience/publishing status; privately verify first founder's Google subject/email.                                            |
| Manual configuration required | Select tailnet owner, coordinator identity/address, device grants and API split-DNS mechanism; authorize installation/configuration separately.                       |
| Implementation required       | Single-use worker enrollment is still a plan. Separately authorize its implementation and replay/expiry/ownership tests before worker onboarding.                     |
| Release blocked               | Review and commit release work, then build/test a new immutable version from a clean revision. Current HEAD lacks the release tooling/templates.                      |
| Decision required             | Select encrypted off-server backup destination, key custodian, retention, recovery targets and an approved backup downtime window.                                    |
| Acceptance pending            | Real HTTPS/Google login, invitations/logout/revocation, owner isolation, tailnet source preservation and physical remote Windows/macOS failover.                      |
| Acceptance pending            | Native worker builds/signing/distribution, security/dependency review, audit retention, backup restore drill and actual Droplet capacity monitoring.                  |
| Authorization required        | Approve each external configuration action and deployment separately. This milestone does not complete Phase 10.                                                      |

## Paths and configuration inventory

Canonical host layout: `/opt/the-godfather/{incoming,releases,state}`;
backups: `/opt/the-godfather/state/backups`; private environment:
`/opt/the-godfather/production.env`; successful release pointers:
`/opt/the-godfather/state/{current,previous}`. The prepared directories are root-owned;
state/backups are mode 0700. Choose a dedicated operator or explicitly accept root
operation; do not silently grant Docker membership or change directory ownership.
Container paths such as `/var/lib/godfather/artifacts` and Docker's named volumes
are intentionally different from host deployment paths.

Every key in `infrastructure/release/production.env.example`:

| Key                                  | Requirement and source                                                                                                                     |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `POSTGRES_PASSWORD`                  | Always required; unique cryptographic random value with at least 32 bytes of entropy. Shared by PostgreSQL and API/migration runtime only. |
| `GODFATHER_GOOGLE_CLIENT_ID`         | Always required; dedicated production Web application OAuth client ID.                                                                     |
| `GODFATHER_GOOGLE_CLIENT_SECRET`     | Always required; Google-issued client secret, delivered privately to API/migrate only.                                                     |
| `GODFATHER_GOOGLE_BOOTSTRAP_SUBJECT` | First fresh installation only: independently verified Google `sub`. Clear after successful bootstrap.                                      |
| `GODFATHER_GOOGLE_BOOTSTRAP_EMAIL`   | Matching Google-verified email; use with subject, never alone. Otherwise leave both bootstrap keys blank.                                  |
| `ACME_EMAIL`                         | Always required; monitored operator email for certificate notices.                                                                         |

Generated `release.env` supplies five required immutable image selectors:
`API_IMAGE`, `DASHBOARD_IMAGE`, `POSTGRES_IMAGE`, `REDIS_IMAGE`, `CADDY_IMAGE`.
Do not hand-edit these or override them from the shell/private file. Installer
checks selected images against `image-ids.txt`. Required operator variables are
`GODFATHER_ENV_FILE=/opt/the-godfather/production.env` and
`GODFATHER_STATE_DIR=/opt/the-godfather/state`; there is no required release-root
variable because scripts locate their own release directory.

Compose fixes `GODFATHER_ENVIRONMENT=production`,
`GODFATHER_WEB_ORIGIN=https://app.the-godfather.ai`, database host/name/user
`postgres/godfather/godfather`, session lifetime 28800 seconds, authentication limit
20 requests per direct peer/action/minute, lease 30 seconds, heartbeat 10 seconds,
suspect 20 seconds and offline 30 seconds. Migrations use a 30-second DB timeout.
Dashboard backend is `GODFATHER_API_URL=http://api:8000`; keep this internal bridge.
API image fixes artifact storage at `/var/lib/godfather/artifacts`.
Changing these fixed values requires a reviewed release change; adding arbitrary
keys to `production.env` does not automatically inject them into containers.
No operator session-signing secret is required by the present PostgreSQL-backed
opaque-session design. Tailscale and worker credentials are separate from this file.

## DNS records to enter after authorization

The prepared host was `137.184.227.74`. Reconfirm this IPv4 belongs to the intended
Droplet and verify control of `the-godfather.ai` before entering these records:

| Type | Zone-relative name | Full name              | Value            | TTL         |
| ---- | ------------------ | ---------------------- | ---------------- | ----------- |
| A    | `app`              | `app.the-godfather.ai` | `137.184.227.74` | 300 seconds |
| A    | `api`              | `api.the-godfather.ai` | `137.184.227.74` | 300 seconds |

Use direct DNS-only records for the initial Caddy deployment. Review/remove
conflicting A/AAAA/CNAME records only under separate authorization. Do not add AAAA
until a real assigned IPv6 address, firewall and routing are tested; existing stale
AAAA records also need attention. Review inherited CAA restrictions against Caddy's
chosen ACME issuer. No apex, wildcard, MX or registrar change is needed here.
After application deployment is separately approved, verify both names against
authoritative/public resolvers and test certificate issuance/renewal.

Worker-only resolution must map `api.the-godfather.ai` to the coordinator's approved
Tailscale address, retaining the public hostname for TLS SNI/certificate validation.
The address is not known yet. Use an explicitly managed host mapping or an approved
split-DNS resolver that answers the API name; MagicDNS alone does not create this
custom-domain record. Avoid accidentally shadowing the public app name/whole zone.
Keep public DNS available for ACME validation. Do not enable Tailscale Funnel.

## Google Cloud and founding administrators

Operator steps, not executed:

1. Select an operator-controlled Google Cloud project. In Google Auth Platform,
   configure Branding/support contacts and authorized domain `the-godfather.ai`
   where requested, after domain control is verified.
2. Choose External audience when founders use different Google organizations or
   personal accounts; Internal is suitable only if all intended users belong to
   the same eligible organization. Select Testing/production publishing deliberately;
   add approved Google test users where required. This never grants Godfather access.
3. Create a separate **Web application** production client. Authorized redirect URI,
   exactly, with no trailing slash:
   `https://app.the-godfather.ai/api/auth/callback`.
   The API hostname is not the callback. Leave JavaScript origins empty for this
   server authorization-code flow; no Google browser SDK is used. Keep development
   localhost redirects in a separate development client.
4. Request only `openid email profile`. No Gmail/Drive API, service account or
   offline refresh-token permission is needed. Store the client secret privately.
   Google requires exact redirect matching; see its
   [OIDC configuration and verification reference](https://developers.google.com/identity/openid-connect/openid-connect).
5. Before first startup, obtain the first founder's stable `sub` and verified email
   through an operator-controlled OIDC flow. Use a maintained verifier to check the
   Google-issued ID token's signature, issuer, intended client audience, expiry and
   `email_verified=true`; validate the flow's state/nonce/PKCE. Follow
   [Google's token verification guidance](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).
   An email, Google Cloud project number or decoded/unverified JWT is insufficient.
   Token acquisition/verification is a prerequisite, not implemented by this
   checklist; retain the verified identity mapping privately, never the raw token
   in Git/chat/logs. No production identity has been verified in this milestone.
6. For a new empty database, privately set both bootstrap keys to that identity.
   At a separately approved deployment, migrate explicitly, then sign in at the app
   with that Google account. Code serializes onboarding and permits bootstrap only
   when there are no Google identities and no existing platform administrator.
   It validates subject plus verified email and audits `administrator_bootstrapped`.
7. Clear both bootstrap values after success. Recreate API configuration with the
   private Compose invocation below (`up -d --no-deps --force-recreate api`); a
   restart does not update environment variables. Subsequent migration containers
   read the cleared file. Verify admin access still works.
8. At `/administration`, use **Invitations** to invite the second verified email
   with role `platform_admin`. Deliver the one-time invitation token privately;
   the invitee enters it at first Google sign-in. Verify equal application roles,
   invitation-only denial, logout/revocation and each owner's host restrictions.
   Application invites are distinct from the still-missing worker enrollment grants.

For an existing database, preserve user UUIDs and ownership. Bootstrap refuses an
unrelated replacement admin. After a backup and independent subject verification,
use the existing offline identity-link CLI through the approved production Compose
context: `exec -T api python -m godfather_api.identity link --user-id EXISTING_UUID
--subject VERIFIED_SUB`. Do not migrate development fixtures to production or
match/merge users by email. See [Phase 09 operations](phase-09.md).

## HTTPS, public routes and Docker boundaries

Caddy names both hosts explicitly, enables automatic HTTPS/HTTP redirects and adds
HSTS (one year, no preload/includeSubDomains). It persists certificates/config in
`caddy-data`/`caddy-config`; request bodies are limited to 2MB and access logging is
disabled to protect OAuth query parameters. Certificate issuance needs correct DNS,
reachable challenge ports and writable persistent storage; offline syntax validation
does not prove these. See [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).

| Incoming route                                                                        | Expected behavior after deployment                                                                                                        |
| ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| HTTP app/API host                                                                     | Redirect to HTTPS; ACME challenges handled by Caddy.                                                                                      |
| HTTPS app `/`, `/administration`, `/api/auth/*`, `/api/control/*`                     | Proxy to dashboard:3000; dashboard bridge allowlist and API sessions/authorization enforce access. Login itself is reachable anonymously. |
| HTTPS API `/api/v1/workers` and `/api/v1/workers/*`, public source                    | 403, before backend access.                                                                                                               |
| Same worker routes, approved tailnet source                                           | Proxy to API:8000; valid machine credential, enabled owner/node and contribution policy still required.                                   |
| HTTPS API all other paths, including `/health/*`, `/docs`, `/openapi.json`, human API | 404, including over Tailscale.                                                                                                            |

Only Caddy publishes TCP 80/443 and UDP 443 (HTTP/3). API/dashboard have no host
ports; migration is tools-profile-only. PostgreSQL/Redis have no host ports and
attach only to `backend` with `internal: true`; API joins backend/frontend,
dashboard/Caddy frontend, migration backend only. Caddy admin port 2019 remains
inside its container. No host Docker socket, source tree or inference endpoint is
mounted/exposed. Redis is transient and is not used as the durable job store.

The tailnet matcher uses the actual socket peer (`remote_ip`), not a caller-supplied
forwarded header. Prove source preservation on actual Ubuntu/Docker with a real
worker before onboarding. Do not widen to Docker bridge/private ranges or trust
arbitrary X-Forwarded-For if it fails. Any extra proxy/Serve changes need review.
The API deliberately disables proxy-header trust; auth throttling is currently an
aggregate dashboard-peer limit, not a public per-user/per-IP perimeter rate limit.
No additional edge rate limiter was added; review adequacy before public exposure.
Docker-published ports require Docker-aware firewall checks, not reliance on UFW
alone: [Docker firewall behavior](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## Minimal DigitalOcean Cloud Firewall proposal

Create a named firewall for this coordinator and attach it to the exact intended
Droplet only after approval. Review other attached firewalls for broader rules.
Required inbound allow rules; all other unsolicited inbound traffic stays denied:

| Protocol | Destination port | Allowed sources                                                                                                                                      |
| -------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| TCP      | 22               | Approved administrator public IPv4 addresses as individual `/32` CIDRs; approved IPv6 `/128` only if used. Values must be supplied by the operators. |
| TCP      | 80               | `0.0.0.0/0`; add `::/0` only with approved IPv6 support.                                                                                             |
| TCP      | 443              | `0.0.0.0/0`; add `::/0` only with approved IPv6 support.                                                                                             |

Keep the existing SSH session and DigitalOcean recovery console available; after
attachment, prove a second SSH login from every approved source before disconnecting.
Do not guess home IPs from city names or open SSH globally to avoid this decision.
For changing residential IPs, choose a stable administration egress or a reviewed
allowlist-update/recovery procedure. Do not change SSH authentication in this task.

Initially keep outbound TCP all ports, UDP all ports and ICMP to all destinations
(IPv4/IPv6), the simple compatibility policy for DNS, ACME, Google discovery/token
and key endpoints, time synchronization, updates and Tailscale relay/NAT traversal.
This is intentionally broad outbound access; tighter egress requires a separate
tested policy. [DigitalOcean rules are stateful](https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/).
UDP 443 inbound is optional for HTTP/3; omit it from the minimum policy despite
the Compose binding. Tailscale can use relays without public inbound worker ports;
opening its confirmed UDP listening port (normally 41641) for better direct
connectivity is an optional separately approved decision, not TCP API access.
See [Tailscale firewall requirements](https://tailscale.com/docs/reference/faq/firewall-ports).
If enabling IPv6, also review necessary ICMPv6 behavior. Never allow public
5432, 6379, 3000, 8000, 2019, 2375/2376 or model/worker administration ports.

## Worker networking and unfinished enrollment

Workers initiate outbound HTTPS to the API hostname over Tailscale. Agree tailnet
ownership, coordinator tags, tag ownership and grants for explicitly approved
devices/users to coordinator TCP 443 only. Do not grant access to owner home LANs,
files, shells or databases. Network membership is not application authorization;
reusable machine credentials remain separate from Google human sessions.

The current worker credential binds an owner and node, supports reconnect/revocation,
and preserves lease/fencing protections. It is not a short-lived enrollment token.
The [enrollment plan](worker-distribution.md) still needs an additive durable grant
model, single transactional consumption, expiry/replay/concurrency and owner tests,
local machine-secret generation/storage, revocation and failure reconciliation.
Do not ship reusable credentials as enrollment grants or claim onboarding ready.
Native macOS builds, signing/notarization, clean-host installation and real remote
disconnect/failover remain open; local/synthetic evidence cannot close those gates.

## Secrets: future private installation, not executed

Use the approved root/operator session on the host after authorization. Never reuse
development credentials. The following example requires Bash/OpenSSL, generates
only the database password, refuses an existing file and prints no secret values:

```bash
set +x
(
  set -eC
  umask 077
  db_password=$(openssl rand -hex 32)
  {
    printf 'POSTGRES_PASSWORD=%s\n' "$db_password"
    printf '%s\n' 'GODFATHER_GOOGLE_CLIENT_ID=' 'GODFATHER_GOOGLE_CLIENT_SECRET=' \
      'GODFATHER_GOOGLE_BOOTSTRAP_SUBJECT=' 'GODFATHER_GOOGLE_BOOTSTRAP_EMAIL=' 'ACME_EMAIL='
  } > /opt/the-godfather/production.env
  unset db_password
)
```

Use a trusted editor with swap/backup files disabled to fill remaining values
privately from Google's client configuration, the verified identity mapping and
the certificate contact. Preserve dotenv quoting for special characters. Verify
owner and mode with `stat -c '%U:%G %a %n' /opt/the-godfather/production.env` (expect
approved owner and 600), never `cat`. Keep the file outside checkout/releases and
encrypted in an approved secret backup. Repository and Docker ignore rules now
exclude files named `production.env`; this is a safeguard, not a secret detector.

Future private Compose invocation, after an approved release is installed:

```bash
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
release_dir=$(readlink -f /opt/the-godfather/state/current)
production_compose() {
  docker compose --project-name godfather-production --project-directory "$release_dir" \
    --env-file "$release_dir/release.env" --env-file "$GODFATHER_ENV_FILE" \
    -f "$release_dir/compose.production.yaml" "$@"
}
production_compose --profile tools config --quiet
```

Use quiet validation; expanded `compose config`, `config --environment`, container
inspection and shell tracing can disclose secrets. Do not source `production.env`
as shell code, place secrets in CLI arguments, or capture OAuth codes/cookies in
logs/screenshots. Trusted root/Docker operators can inspect runtime environment;
accept that trust model explicitly or authorize stronger secret-store integration.
Rotate Google credentials through the issuer and recreate affected services.
Changing the password file alone does not rotate an existing PostgreSQL role;
coordinate database role/config changes in reviewed maintenance. Worker secrets
stay in owner-controlled stores; BYOK is still planning only.

## PostgreSQL backups and decisions

`scripts/backup.sh` takes deployment/backup locks, stops Caddy/dashboard/API,
creates a custom-format `pg_dump`, checks `pg_restore --list`, archives artifacts,
checks gzip integrity and writes paired checksums plus release metadata. Ordinary
backup attempts to resume the previously running services, including on error;
upgrade backup keeps them stopped. Select only a complete backup with both payloads
and verified SHA256SUMS; incomplete directories may remain after failure.

Location: `/opt/the-godfather/state/backups/UTC-PID` (private, unencrypted on this
host). There is no installed schedule, automatic retention, encryption or off-server
upload. Release images, `production.env`, Caddy TLS volumes and tailnet credentials
are not included; protect/recover those separately. Redis needs no durable backup.
The prior local release test restored DB/artifacts in isolation; it did not prove
encrypted off-site recovery. Full logical dumps give no continuous WAL/PITR here.

Operator decisions before production: choose off-server storage/provider/region,
retention/deletion policy, RPO/RTO, daily/pre-upgrade schedule and downtime window,
backup alert owner, encryption tool/key custody and restore-drill frequency. A
reasonable proposal is daily plus pre-upgrade backups, 7 daily/4 weekly/6 monthly
copies, but these targets are not configured or accepted. If daily dumps cannot
meet the required RPO, separately design/test a different backup strategy.

Encrypt the complete paired backup on the host before transfer, preferably to an
off-server-held decryption key; use scoped upload credentials and test decryption
from another environment without relying on the failed Droplet. Keep a separately
encrypted secret/release recovery set. Do not delete local copies until an off-site
copy and restore are verified; schedule retention cleanup only after approval.
Restores use new empty DB/artifact volumes and matching release/schema; never
automatically overwrite production or run `down -v`.

## Clean committed source and validation evidence

Observed HEAD: `4304e4a10dcd24a65610ac78d056a7333e479621` (Phase 09).
Release tooling, templates, guides and tests are still untracked, with tracked
application/release edits also present. `git ls-tree` confirms HEAD lacks
`scripts/release.py`, `scripts/check_release.py` and `infrastructure/release`.
Therefore a clean rebuild from the current committed revision is **not verified
and cannot contain this release configuration**. No commit/push or new release
archive was made in this milestone; Phase 10 is not complete.

The existing rc.3 manifest has `source_dirty=true`. Its checksums and original
INSTALL.md/common.sh still describe the older path; do not patch those immutable
files in place or deploy rc.3 as a final clean release. The active source guide
now uses the correct base. A new immutable version must include these corrections.

After review and commit (and authorized GitHub save before advancing phases), use
a clean local worktree at the exact approved commit, not the working directory's
uncommitted files. Example future build steps on a build host with Git/uv/Docker:

```powershell
$sourceRevision = git rev-parse HEAD
git worktree add --detach '../Godfather-release-clean' $sourceRevision
Set-Location '../Godfather-release-clean'
if (git status --porcelain) { throw 'Release source is dirty' }
uv run --locked --all-packages python -m scripts.release --version 0.1.0-rc.4
uv run --locked --all-packages python -m scripts.check_release dist/godfather-0.1.0-rc.4-linux-amd64
$manifest = Get-Content dist/godfather-0.1.0-rc.4-linux-amd64/manifest.json -Raw | ConvertFrom-Json
if ($manifest.source_dirty -or $manifest.source_revision -ne $sourceRevision) { throw 'Invalid provenance' }
```

Use another unused version if rc.4 exists. A new clean worktree needs normal
locked tooling installation and package/registry access; builders must never copy
production secrets. Retain test output, manifest, image IDs/digests and archive
hash. Byte-identical rebuilds are not guaranteed: upstream image tags can move;
digest pinning/build reproducibility is a further hardening decision.

Files changed in this milestone: this checklist, `README.md`,
`docs/operations/production-release.md`, the comments in
`infrastructure/release/{production.env.example,scripts/common.sh}`, and
`production.env` exclusions in `.gitignore`/`.dockerignore`. Existing application,
installer, Compose and Caddy behavior was preserved; earlier uncommitted release
work was not reverted or committed.

Executed during this review: production Compose parsed with `--no-interpolate`
(no secrets or services); existing Caddy image validated the unchanged Caddyfile
with `--network none` and a nonfunctional contact address (no listener/certificate
request); 9 existing release unit tests passed; all three maintenance scripts
passed offline `bash -n`; Markdown formatting, patch whitespace, active-path
consistency and root/nested `production.env` Git exclusions passed. These are
configuration/unit checks, not Google/DNS/Tailscale integrations. Earlier broader regression and
isolated DB/proxy/restore evidence is in the
[release validation report](release-validation-2026-10-20.md); it was not rerun here.

Stop here. Resolve the decisions and authorize external configuration explicitly;
do not transfer archives or start application containers under this milestone.
