# Command Center UI deployment - 2026-10-22

The owner explicitly authorized deploying the Command Center to the existing VPS
and prohibited new worker builds. Coordinator **0.4.1-rc.6 is deployed** at
https://app.the-godfather.ai. Existing **Consigliere 0.4.1-rc.4** installers and worker
configuration are unchanged. No native worker build or publication ran.

## Immutable release and upgrade

- Code: `e9be6a134de16e23e4bc6ece7a48faf8e2e70037`, clean detached worktree.
- Coordinator build started: `2026-10-22T15:04:21.885731+00:00` (UTC).
- Package: `.cache/ui-release-0.4.1-rc.6/dist/godfather-0.4.1-rc.6-linux-amd64.tar.gz`.
- SHA-256: `1d7cfa4253cc63ad840cc7862c40886fdd2ad37a20328530761235db0eef7985`.
- Current VPS release: `/opt/the-godfather/releases/godfather-0.4.1-rc.6-linux-amd64`.
- Previous release: `0.4.1-rc.5`; its package/images are retained.
- Schema: additive migration `0014_command_center_appearance` applied by the
  existing explicit upgrade installer. No database image change or restore occurred.

Built only the coordinator from the tested source and reused the checksum-verified
existing downloads. Local release validation passed image IDs/architecture/content,
private services, fresh/repeat migrations, proxy/authentication gates, published
downloads, database/artifact restore and persistence through restart. This local
validation used isolated containers and disposable data.

SSH used the repository-documented PuTTY trust/authentication configuration, with
batch host-key verification. OpenSSH's default identity was unavailable; no new key,
password or trust exception was configured. A slow SFTP archive transfer was replaced
with SCP and the complete archive matched its trusted local hash. The first streamed
shell invocation did not run the installer because a nested command consumed stdin;
the release pointer was verified unchanged, then uploaded scripts were executed by
filename with stdin closed. The actual installer completed successfully once.

## Live preservation and recovery evidence

Before maintenance there were no assigned/running jobs. The installer took a quiesced
paired backup, then upgraded and restarted the existing Compose project. Backup:
`/opt/the-godfather/state/backups/20261022T151201-1146352`. Its checksums, PostgreSQL dump
listing and artifact gzip integrity passed. Production restore was not performed.

Postflight verified all five services healthy, exact source/version/build metadata,
exact migration head, and private API/dashboard/PostgreSQL/Redis host ports. Only the
existing Caddy proxy publishes application ports. Production environment bytes and
mode 600 were preserved, including the existing vault/proxy configuration.

Stable record fingerprints were preserved for 2 users, 2 Google identities,
3 workspaces, 1 membership, 4 machine/human credentials, 2 node ownership/policy
records, 9 jobs, 4 agent versions, 6 artifacts, 3 checkpoints, 2 provider connections
and 1 encrypted account key. The new credential timestamp was excluded from the
before/after fingerprint solely to account for its additive null column. No account
key was decrypted. Both existing nodes returned online/online after the upgrade.

All existing download bytes, including the manifest, matched the previous release:

| Existing worker installer | SHA-256                                                            |
| ------------------------- | ------------------------------------------------------------------ |
| Windows x64               | `afc574522c8f22f0407e6fe1ff366031ffabcc56ad355f9d2cdd40850c1f93aa` |
| Mac Apple silicon         | `e81f3f145b20bb5660ffdd2efbb1a48d3c74d315142a987d617311db7c87280e` |
| Mac Intel                 | `b3a477dfef26ce271472b8ce5b56464df6ff72ffafeea574cc66fa9de6ca1b98` |

## Public checks and limits

All 50 public HTTP checks passed over normal DNS and verified TLS. Anonymous
private API access, unauthenticated worker requests and foreign-origin mutations
remain denied, including the new appearance and computer-credential deletion
operations. All six installer downloads (three platforms on both existing hostnames)
returned HTTP 200 and matched the preserved SHA-256 hashes.

The live browser used normal DNS and verified TLS. It confirmed the login screen,
Overview Jobs/Nodes icons, and the Appearance page's sign-in redirect, with no browser
runtime errors. Authenticated appearance editing, owner/audit tooltips and credential
deletion had already passed the isolated browser and real PostgreSQL tests recorded
in [the implementation report](command-center-ui-2026-10-22.md). Deployment checks did
not use a private user account, modify visual preferences, delete a credential,
submit a job, run inference, download a model or change contributor host permissions.

Evidence is ignored under `.cache/command-center-deployment-2026-10-22/`; server-side
fingerprints and backup references are under
`/opt/the-godfather/state/deployments/command-center-ui-20261022-rc6`.

Existing workers do not retrospectively report their installer version. They remain
compatible and display Not reported until a separately authorized native worker build
is installed. No new worker build, upgrade or Phase 13 work is authorized by this run.
