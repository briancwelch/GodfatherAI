# Shared Inference feedback release, 2026-10-24

The owner authorized building and deploying this correction on 2026-10-24.
Command Center and Windows x64, Apple Silicon and Intel Mac installers are now
published as **0.10.0-rc.5** at [Command Center](https://app.the-godfather.ai).
All five coordinator services passed live health checks.

## Delivered behavior

Workers offer right-click **Delete setup**, a matching visible button and keyboard
access, with a scope-specific confirmation. The initiating computer removes its
whole setup; another participant removes its own invitation and approval. Either
operation stops the group. Model files, node identities, owner restrictions and
job history are retained. Existing setups were preserved during deployment.

Approval, withdrawal, deletion, device detection, refresh and wizard requests show
pending and completion/error feedback beside the controls. Duplicate requests are
disabled, confirmed mutations update the list immediately, and old refresh
snapshots cannot undo them. Validation and cancellation explain their outcomes.

Migration **0018_shared_engine_removal** adds setup deletion markers and per-node
dismissal without deleting historical records. Tombstones reject stale managed
engine advertisements. Earlier workers retain compatible response payloads.

## Release verification

All artifacts use clean source `85ab117dfcfbd80cd4ad3b948c19b74f5b5646ef`. The initial CI run caught one test
importing the optional Tk module before its skip guard; the corrected test is
included here. Rc.4 was not published. Final native builds use the exact full
commit and passed on both architectures.

- [All eight source CI jobs](https://github.com/briancwelch/GodfatherAI/actions/runs/40113272049)
  passed across Windows/macOS/Linux, Python 3.12/3.14, dashboard formatting/lint,
  types/tests/build/audit, PostgreSQL and process recovery checks.
- Full local disposable PostgreSQL suite: **303 passed**. Source validation also
  passed **458 non-integration tests**, with four existing optional skips; focused
  feedback checks, strict mypy and Ruff passed.
- [Both native Mac build jobs](https://github.com/briancwelch/GodfatherAI/actions/runs/40113464762)
  passed packaging, architecture/library inspection and startup checks.
- Windows installer passed temporary install/reinstall, packaged Tk/tray startup
  and isolated OS credential-store checks. Frozen-code inspection confirmed the
  new deletion contract, context menu and approval/withdrawal feedback.
- All **10 packaged release gates** passed, including provenance, repeat
  migrations, authenticated proxy boundaries, all installer downloads, actual
  disposable database/artifact restoration and restart persistence.
- Native Windows fixtures verified visible actions and nearby feedback at
  1120 x 760 and 760 x 600. No models were loaded or owner approvals created.

Coordinator archive: `godfather-0.10.0-rc.5-linux-amd64.tar.gz`,
**420,181,950 bytes**, SHA-256
`0254289d8405349c4212c6d5b7043c3555d439cfe7a9efcbc41ed3d21b575978`. The checksum was verified on the VPS before activation.

| Installer                                                                                                       | SHA-256                                                            |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [Windows x64](https://app.the-godfather.ai/downloads/consigliere-0.10.0-rc.5-windows-x64-setup.exe)             | `18bfe2c62719c1a9d490844fff7f6c147f12bb6ac66f1b17e6b3036c2dba1bfc` |
| [Mac (Apple silicon)](https://app.the-godfather.ai/downloads/consigliere-0.10.0-rc.5-macos-arm64-installer.dmg) | `d0c69392a4835a54bca9d48e7085e3468108ad68bcb1ba59ce77a9bd858da640` |
| [Mac (Intel)](https://app.the-godfather.ai/downloads/consigliere-0.10.0-rc.5-macos-x64-installer.dmg)           | `0c623e9ebc0d68636c5c72e35470d5df521a7c45b3d4b7d64677999b7ba968db` |

The existing unsigned Windows/ad-hoc Mac signing policy is unchanged. Developer
ID/notarization and SmartScreen acceptance are not claimed.

## Deployment and preservation

The backup-first upgrade activated
`/opt/the-godfather/releases/godfather-0.10.0-rc.5-linux-amd64` and migration
**0018_shared_engine_removal**. Only Caddy publishes host ports; API, dashboard,
PostgreSQL and Redis remain private. No active jobs were present at activation
or postflight. Node health after deployment: 3 offline, 2 online.

All **17 stable-record fingerprint groups** passed preservation checks, including
existing shared setups/approvals, credentials, encrypted keys, ownership and
contribution policies, settings, jobs and artifacts. This includes all five node
identities, 31 jobs, two shared setups and two per-node consents. Production
environment bytes and mode 600 were unchanged. Detailed fingerprints and counts
are retained in the deployment evidence.

Paired backup: `/opt/the-godfather/state/backups/20261024T170401-2431172`. Checksums, PostgreSQL archive listing and artifact gzip
integrity passed. Actual restore was exercised in the isolated package gate.
Server evidence is under
`/opt/the-godfather/state/deployments/shared-engine-20261024-feedback-rc5/`.

All **118 normal-TLS public checks** passed, including installer checksums on
both public hostnames and anonymous denial of the new worker delete endpoint.
No production setup was deleted and no new account, node, job, provider key or
participation approval was created for acceptance.

Owners receive the worker via **File > Check for updates** or Nodes > Downloads.
Installed contributor apps were not forcibly replaced. No model-weight download,
paid inference or contributor-host setup was performed. Multi-GPU/multi-computer
inference remains a separate hardware acceptance item. Cleanup was deferred.

Local receipts are in `.cache/shared-engine-release-0.10.0-rc.5/`.
