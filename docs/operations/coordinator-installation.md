# Install and maintain a Command Center

Most users only need the existing Command Center address and Consigliere. Follow
this guide when you are the administrator hosting a coordinator. The current
published package is **0.8.0-rc.1**. Obtain the archive and trusted SHA-256 from
your release administrator; this private project does not have a public download
release feed. The [release report](shared-inference-deployment-2026-10-22.md)
records the existing deployment and package checks.

## Prepare Docker and sign-in

Use a Linux AMD64 host with Docker Engine and Compose v2.20 or newer. Install
Docker and its Compose plugin using the instructions for your Linux distribution,
then confirm:

```bash
docker --version
docker compose version
docker info
```

The release installer checks Docker; it does not install Docker or system services.
Its initial capacity target is at least 2 vCPUs, 4 GB RAM and 15 GiB free disk, with room
for growing data and backups. Use an independent always-on host for shared use.
For local development on Windows, install Docker Desktop with WSL2 and follow the
[local setup guide](setup.md). The packaged Linux coordinator is a separate install
flow from that development checkout.

Before first install, prepare a hostname resolving to your host, HTTPS/certificate
ports 80 and 443, and a Google Web OAuth client. Set its redirect URI to
`https://YOUR-HOSTNAME/api/auth/callback`. Keep the Google client secret private.
Only the web proxy publishes ports; databases, models and worker administration
must remain private. Workers normally connect outward through authenticated HTTPS.
Tailscale is optional for worker transport.

## First install

Place the release archive and checksum together and compare the expected digest
with your trusted release record. Then:

```bash
sha256sum -c godfather-0.8.0-rc.1-linux-amd64.tar.gz.sha256
tar -xzf godfather-0.8.0-rc.1-linux-amd64.tar.gz
cd godfather-0.8.0-rc.1-linux-amd64
bash scripts/setup.sh
```

Run setup interactively. Enter your hostname, founder Google email, Google OAuth
client ID/secret and installation data folder (normally `/opt/the-godfather`).
Setup generates private database/proxy/vault values, saves `production.env` with
mode 600, loads the packaged images, applies migrations and starts the services.
Do not run first setup over an existing installation.

Open your HTTPS address and sign in with the configured founder Google account.
Invite additional users through Administration; choose platform administrator only
for people who should administer shared services. Invite them to the intended
workspaces separately. See [founder sign-in](founder-bootstrap.md) and
[user onboarding](user-onboarding.md).

## Check status

From an extracted release directory:

```bash
export GODFATHER_ENV_FILE=/opt/the-godfather/production.env
export GODFATHER_STATE_DIR=/opt/the-godfather/state
bash -c 'source scripts/common.sh; compose ps'
```

Keep the same private environment and persistent state paths across upgrades.
Do not print `production.env` or expanded Compose configuration to logs or chat.

## Upgrade and back up

Obtain and verify the next release, then extract it into a new directory. From
that directory, with the two environment variables above set:

```bash
bash scripts/install.sh upgrade
bash -c 'source scripts/common.sh; compose ps'
```

The upgrade procedure takes a paired database/artifact backup before changing
services. To make a separate backup, run `bash scripts/backup.sh` from the current
release with the same environment variables; this briefly stops web/API services
and restarts them afterward. Schedule the brief interruption when it is acceptable to users. Preserve
the existing private environment, database, artifact storage, worker identities and
provider vault key. Keep a protected separate copy of the environment/vault key;
a database backup alone cannot recover encrypted account connections.

Follow [complete coordinator recovery](coordinator-recovery.md) (packaged as
`RECOVERY.md`) to capture the matching encrypted configuration separately, escrow
its independent recovery key, and verify a restore before reopening traffic. New
data backups include `recovery.json`; a complete recovery set also needs that
separate configuration export and the matching trusted release.

Retain the current release and five predecessors, and keep backups under their
own reviewed retention policy. An older image is not automatically compatible
with newer database records. Inspect the release's packaged `DEPLOYMENT.md` recovery
procedure before recovery; use a compatible forward fix or an approved
paired database/artifact restore when required. Do not delete volumes to upgrade.

## Add workers

In Command Center choose **Nodes > Downloads**, install Consigliere on the intended
computer, and complete its browser pairing. Owners choose their local permissions
and workspace contribution. They do not need the coordinator's Docker files,
database password or Google OAuth client secret. See the [user guide](../../README.md).
