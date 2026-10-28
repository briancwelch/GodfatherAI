# Worker activity and LAN approval release, 2026-10-28

The owner authorized new worker builds, GitHub push and production deployment.
Coordinator and all three native worker installers are published as
**0.12.0-rc.2** at [Command Center](https://app.the-godfather.ai).
All five production services passed health checks. Contributor computers were
not updated automatically; use **File > Check for updates** on both workers.

## Delivered behavior

- **Jobs** lists this node's active and historical execution attempts, including
  shared inference participation, with workspace, status and local timestamps.
  It reads existing PostgreSQL records and supports 25-item pagination.
- **Notifications** provides unread counts, an always-visible notice bar, saved
  local history and actions that open the relevant job or shared setup. Shared
  invitations explain approval/joining; the initiator is prompted when it must
  start. Job start, completion, cancellation and failure use durable events.
  Opening a notification never approves or starts work.
- Shared Inference shows saved participant endpoints, restores the selected
  setup's saved address and preserves unsaved edits during refresh. Approval
  confirmation names the chosen endpoint. Start rejects unsaved address changes.
  LAN addresses precede Tailscale addresses in the initial list. The final owner
  approval updates stale waiting feedback without replacing unrelated errors.
- Job details and notification guidance reserve layout space and wrap to the
  window width; expanding tables cannot crowd them out at compact sizes.

The existing worker already transmitted the address selected at approval time;
startup uses that saved endpoint. There was no verified Tailscale substitution.
Changing the dropdown requires **Approve this computer** again. With Carbon as
initiator, Carbon connects to Radium's approved address/port. The peer listener
starts after **Configure and Start**, rather than merely after approval.

See [setup and implementation details](worker-activity-and-lan-2026-10-28.md).

## Validation

- Release source: `1599e73c4f6d079e1b2c47e9e44e84a6af958323`, incorporating
  `0aaf8c9` and the compact-layout correction. Source was clean and built from an
  isolated detached worktree. [All eight CI jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/40755867022),
  including Windows/macOS/Linux checks, Python 3.12/3.14, dashboard build/audit,
  PostgreSQL integration, restart/outage and durable agent recovery.
- Both [native Mac builds and checks passed](https://github.com/briancwelch/GodfatherAI/actions/runs/40755867065):
  Apple Silicon and Intel DMGs, native GUI lifecycle, bundled libraries and
  packaged startup. Windows passed temporary installation/repeat, packaged
  Tk/tray startup and an isolated OS credential-store check. Normal installed
  identities and credentials were not used by these fixtures.
- Local Python/PostgreSQL suite: **789 passed, 32 skipped**. Windows
  non-integration: **490 passed, 5 skipped**, followed by **70 final targeted
  worker tests**. Ruff, strict mypy, native desktop/compact UI acceptance,
  dashboard lint/types and **68 dashboard tests** passed. Container GUI skips
  are expected because its optional Tk library is unavailable.
- All **11 immutable-package gates passed**, including exact image provenance,
  migrations, private proxy boundaries, all published installer downloads,
  actual disposable database/artifact restore and restart persistence.
- All **15 live verified-TLS HTTP checks passed**. All three installer hashes
  matched on both public hostnames. The new activity endpoint rejects anonymous
  callers with 401; private job/health routes remain unavailable publicly.
- Live anonymous Edge rendered sign-in on desktop/mobile without page errors.
  Protected polling stopped after 401, with zero additional protected requests
  over the eight-second observation period. Real Google sign-in was not used.
- An internal production read-only evaluation returned **15** historical job
  rows for Carbon and **1** for Radium. It supplied the existing calling
  credential inside an isolated process; it did not exercise public worker
  authentication or an installed worker's signed-in Jobs tab. Authorization,
  node isolation, workspace denial, pagination and event delivery were exercised
  with real authenticated HTTP requests in disposable integration tests.

The earlier `0.12.0-rc.1` installer candidates remain unpublished. Visual review
found crowded footer text, which was corrected and rebuilt under the new
immutable version before production activation.

## Package and preservation

Archive: `godfather-0.12.0-rc.2-linux-amd64.tar.gz`, **422,004,650 bytes**.
SHA-256: `de76e1d8449b85edcec40043bf1a4040f015ca5970e91aaac6c566c822c8aaa1`.
The checksum was verified on the VPS before extraction and activation.

Installer SHA-256 values, also independently verified against the exact source
revision and native build receipts:

| Platform          | SHA-256                                                            |
| ----------------- | ------------------------------------------------------------------ |
| Windows x64       | `f5c899a4979c7a4b52fad8f47b261e023eb4945c7d80120bef55f51bd127de6c` |
| Mac Apple Silicon | `0e42f6198e1090e2ce8031624b22e064a86593c615a733195803335afc06e930` |
| Mac Intel         | `7edbfc5d48c070c67bfc6c691bf46987e2e9e4a4580f473872b334be2dc3331d` |

Active release: `/opt/the-godfather/releases/godfather-0.12.0-rc.2-linux-amd64`.
The backup-first upgrade created
`/opt/the-godfather/state/backups/20261028T195359-740193`. Backup checksums,
PostgreSQL dump listing and artifact archive integrity passed. Actual restore
was tested only in the isolated package gate, rather than over production data.
Migration head remains **0018_shared_engine_removal**; no schema change was needed.

All **17 stable-record fingerprint groups** were preserved, including 3 users,
5 node ownerships, 8 credentials, 4 workspaces, 33 jobs, 36 artifacts,
18 checkpoints, 11 shared setups, 17 consents and the encrypted account key.
The environment file stayed byte-identical with mode 600. No active job existed
at activation or postflight. One worker was online and four offline, matching
preflight. Previous production releases and installer artifacts were retained.

Only Caddy publishes external ports. API, dashboard, PostgreSQL and Redis remain
private. No firewall, Tailscale, DNS, host permissions, model weights or provider
credentials were changed, and no billable inference was performed.

## Remaining acceptance

Update Carbon and Radium, select each computer's LAN endpoint and approve it,
then select **Configure and Start** on Carbon. Their real LAN inference and GPU
performance still need acceptance on the updated installed workers. The setup
shown in the original screenshot was already withdrawn when inspected; that
read-only snapshot could not establish its previously saved address.

Windows signing and Mac notarization status retain the existing candidate
packaging limitations. Real signed-in browser acceptance and physical GPU
inference were not claimed by this release verification.
