# Shared inference workspace permission release, 2026-10-25

The owner authorized commit, GitHub push and deployment after local validation.
Coordinator **0.11.0-rc.3** is active at
[Command Center](https://app.the-godfather.ai). All five services are healthy.
Existing **0.11.0-rc.1** worker installers were preserved; no worker rebuild or
contributor-host update was performed.

## Delivered behavior

An otherwise authorized shared group remains visible when its generated model
identifier is missing from the selected workspace's allowlist. Distributed Jobs
shows **Workspace permission required**, with **Allow in this workspace** for a
workspace owner or administrator. Approval adds that exact shared identifier,
preserves other model/tool permissions and node-owner restrictions, records an
audit event, and refreshes actual readiness. It does not submit a job.

Refresh Command Center, open **Distributed Jobs**, choose the matching execution
setup and group, then select **Allow in this workspace**. Submit the job separately
after the group becomes Ready. No production workspace grant was changed during
release acceptance.

Implementation and operation details are in the
[source verification](shared-inference-workspace-access-2026-10-25.md).

## Validation

- Clean source: `0bf09e74f79e9299f0343cc4b200d0d79b917a04`, committed and pushed to
  `main`. [All eight CI jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/40237991140),
  covering Windows/macOS/Linux, Python 3.12/3.14, dashboard checks/build/audit and
  container-based persistence, recovery and execution checks. The Linux container
  Python/PostgreSQL suite reported **781 passed, 25 skipped**.
- Local source validation: **479 Python tests passed, 5 skipped**; **39 focused
  PostgreSQL integration tests passed**; **68 dashboard component/polling tests
  passed**; lint, formatting, strict typing and API/dashboard builds passed.
- All **11 immutable-package gates passed**, including clean image provenance,
  repeat migrations, private artifact permissions, proxy authentication,
  installer downloads, actual disposable database/artifact restoration and
  restart persistence.
- An isolated Edge fixture exercised denied approval, prompt preservation,
  disabled selections during approval, the exact workspace/group payload,
  confirmed success and readiness refresh, member denial and missing discovery.
  It reported no page errors and **zero submitted jobs**. Only synthetic data
  and a loopback backend were used.
- All **122 live verified-TLS HTTP checks passed**, including the new approval
  POST's authentication/origin boundary and unsupported GET denial. All three
  unchanged installer hashes were verified on both public hostnames. The broad
  anonymous probe reached the existing failed-worker-authentication throttle;
  only the unfinished probes were retried after the window, with normal expected
  denial responses. No rate limits or production policies were weakened.
- Live anonymous Edge acceptance rendered sign-in on desktop/mobile, recorded no
  page errors, and verified protected polling stops after a 401. Real Google
  login was not performed.
- A read-only internal evaluation of the deployed options function against the
  existing setup returned one group, its matching shared model discovered, and
  **Workspace permission required**, `can_enable=true`, `available=false`. The
  existing setup owner's identity was supplied inside a separate process; real
  browser/session authentication was not exercised by this probe. Its database
  transaction was read-only, and no workspace grant or job was created.

## Package and preservation

Archive: `godfather-0.11.0-rc.3-linux-amd64.tar.gz`, **422,036,528 bytes**.
SHA-256: `e33f45fb3ef69f5d128f6bd09aba6e5e4e61a9b39ae2a1a759995cd1161a5456`.
The archive checksum was verified on the VPS before extraction and activation.
The worker manifest is byte-identical to the prior coordinator release; pinned
PostgreSQL, Redis and Caddy image IDs are unchanged.

The backup-first upgrade created the paired database/artifact backup at
`/opt/the-godfather/state/backups/20261025T221438-3175864`. Backup checksums,
PostgreSQL dump listing and artifact archive integrity passed. Migration head
remains **0018_shared_engine_removal**. Actual restoration was tested only in
the isolated package gate, not over production data.

All **17 stable-record fingerprint groups** were preserved, including 3 users,
3 Google identities, 5 node ownerships, 7 credentials, 4 workspaces, 32 jobs,
36 artifacts, 18 checkpoints, 6 shared setups, 8 consents and 1 encrypted account
key. Workspace permissions, contribution policies, provider connections and
application settings also matched. The environment file remained byte-identical
with mode 600. Three nodes were online and two remained offline, matching
preflight; no active jobs were present before or after activation. Only Caddy
publishes host ports.

Server evidence: `/opt/the-godfather/state/deployments/shared-workspace-20261025-rc3/`.
Local receipts: `.cache/shared-workspace-release-0.11.0-rc.3/`.

Physical multi-computer inference/GPU performance and a real signed-in approval
remain owner acceptance items. No model download, paid provider call, setup
approval, account creation or installer replacement occurred during acceptance.
