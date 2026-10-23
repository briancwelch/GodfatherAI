# Member node registration deployment verification, 2026-10-23

The owner authorized deployment of the tested member-registration correction.
Coordinator **0.9.0-rc.4** is active from clean, immutable source
`944ad3dc7cbb6237276b0568b7a24a6419d6fb9d`. Desktop workers remain **0.9.0-rc.2**;
no worker was rebuilt or updated by this deployment.

## Behavior and authorization

Active, invited members receive `nodes.contribute`, so the existing pairing page,
approval/exchange API, worker authentication and scheduler accept their owned
computers. Existing members need no role promotion or database migration.
The running production API verified this permission for members and contributors
while preserving administrator-only `platform.manage`. Ownership, invitations,
Google-linked identity, local host restrictions and paid-provider consent remain
independent requirements. No production account role was changed.

## Release gates

All eight [CI jobs for the deployed commit](https://github.com/briancwelch/GodfatherAI/actions/runs/40005576126)
passed, covering Python 3.12/3.14, Windows/macOS/Linux, frontend checks/build,
PostgreSQL integration and coordinator/worker/scheduler/inference/workflow recovery.
The implementation's local regression results are recorded in
[ADR 0029](../decisions/0029-trusted-member-node-registration.md).

All ten existing package gates passed, including pinned image provenance,
configuration, repeated migrations, private services, authenticated HTTP
boundaries, worker downloads, isolated database/artifact restoration and restart
persistence. An additional network-disabled check of the packaged API verified
the member permission without granting platform administration.

Archive: `godfather-0.9.0-rc.4-linux-amd64.tar.gz`, SHA-256
`2b7a31c9f985621b36ad6cfc2dfe895fe6a5d813de86ed1af203f2082e7f6fb9`.
The local package is under
`.cache/member-node-release-0.9.0-rc.4/source/dist/`; the exact archive hash was
verified again on the VPS before extraction and activation.

## Production preservation

The backup-first upgrade activated
`/opt/the-godfather/releases/godfather-0.9.0-rc.4-linux-amd64`.
All five services are healthy, all four existing workers reconnected online,
and there were no active jobs at the pre-upgrade gate or postflight check.
Only Caddy publishes public ports. API, dashboard, PostgreSQL and Redis retain
private port bindings. The database head remains `0016_distributed_jobs`.

All fifteen stable-record fingerprint groups were preserved: users, Google
identities, account keys, credentials, node ownership/contribution policies,
workspaces/memberships, agents, jobs, artifacts, checkpoints, provider connections,
application settings and distributed records. The production environment file
is byte-identical and retains mode 600. The worker download manifest is
byte-identical to the preceding release and contains the same three installers.

Backup: `/opt/the-godfather/state/backups/20261023T185747-1873117`.
Its checksums, PostgreSQL archive listing and compressed artifacts validated.
Actual restoration was tested in the isolated package gate, without restoring
over production. Server preservation evidence is under
`/opt/the-godfather/state/deployments/member-node-20261023-rc4/`.

## Public verification

All **100** normal-TLS HTTP checks passed. Anonymous enrollment and credential
creation remain denied, foreign origins remain denied, and the direct public
administration API remains private. All six installer downloads across both
hostnames matched their existing hashes; both runtime catalogs matched.
No real Google account login, new node, provider-key update or paid model call
was performed. Local build, CI, package and public-check evidence is under
`.cache/member-node-release-0.9.0-rc.4/`.

This deployment updates only release-status documentation: `README.md`,
`docs/README.md`, ADR 0029 and this report. Runtime changes were already committed
in the deployed source revision; no further code change was included.

## Recipient acceptance

In Consigliere, start **Connect** again and approve the matching new pairing code
using the invited member Google account. The account can remain Member, and the
existing worker installer is compatible. No real Google login or new production
node was created on the recipient's behalf during deployment verification.
