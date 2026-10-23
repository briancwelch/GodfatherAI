# Image workspace permission usability verification, 2026-10-23

The owner authorized the fix and deployment. Scope is the coordinator and website;
Consigliere 0.9.0-rc.2 remains compatible and its installers are preserved.

## Problem and behavior

An empty workspace model allowlist hid all cloud image models even though the
owner's API connection and computer were ready. The page then incorrectly
reported a missing local image model. The blocker was workspace permission.

The options API now separates permitted and workspace-restricted cloud inventory
while preserving node-owner and private account-key checks. Images displays the
restricted choices and the exact workspace restriction. Owners/administrators can
choose **Allow selected model in workspace** using the existing model-access
endpoint. Members receive administrator guidance. Prompt and selection survive
the permission update; a failed update leaves a visible error and does not enable
generation. The sidebar stops suggesting worker/key setup for this blocker.

The form visibly defaults to an available local provider or an already configured
cloud provider. Users still select an exact model/computer. Manual provider choice
survives refresh. **Generate image** requires an online permitted selection, prompt,
provider billing/data-egress consent and worker-processing consent. Allowing a
model never generates an image. No workspace grant is changed by deployment.

## Validation

- Windows Python unit suite: **379 passed, 4 skipped**. Skips require explicitly
  configured local sandbox images or host symlink permission.
- Complete PostgreSQL integration suite: **282 passed**. The added cases cover
  both providers, empty workspace allowlists, explicit grants, unassignable
  restricted jobs, member denial and private-key inventory isolation.
- Dashboard components: **43 passed**. Ruff formatting/lint, strict mypy (183
  source files), TypeScript, ESLint, Prettier and optimized dashboard build passed.
- Edge browser acceptance passed for restricted inventory, exact blocker,
  rejected and successful explicit grants, retained prompt/selection, member
  guidance, both required consents, no automatic generation, provider-specific
  messages and a manual local choice surviving refresh. Desktop/light and
  mobile/dark layouts had no overflow or browser page errors.

No real provider key was read and no billable generation was performed by these
checks. PostgreSQL tests used the disposable `godfather_test` database. Browser
tests used synthetic model inventory and account references with the actual
optimized dashboard. Physical provider/account generation remains unverified.

## Published release and deployment

Coordinator **0.9.0-rc.3** was deployed on 2026-10-23 from clean, immutable source
`2c6aab32768a69613d02aff2a0047309d65013e9`. All eight
[release CI jobs](https://github.com/briancwelch/GodfatherAI/actions/runs/39985147839)
passed, covering Python 3.12/3.14, Windows/macOS/Linux, dashboard checks and the
Linux container/integration/worker/scheduler/workflow probes.

The Linux AMD64 package is `dist/godfather-0.9.0-rc.3-linux-amd64.tar.gz`, SHA-256
`33936d05bdf2ec069f6c5708c9d13379ef9164757adf5bddc4687329d1f28944`.
The existing release checker passed all ten package gates, including image
provenance, configuration, repeat migrations, private services, authenticated
HTTP boundaries, installer downloads, backup restore and restart persistence.
Additional checks confirmed the packaged API and dashboard contain the new
permission flow with their network disabled.

The existing backup-first upgrade activated
`/opt/the-godfather/releases/godfather-0.9.0-rc.3-linux-amd64`. All five services
were healthy; API/dashboard/PostgreSQL/Redis retained private port bindings. The
live API reported the exact version/source revision and the new options fields.
The schema remained `0016_distributed_jobs`. All four existing workers reconnected
online and no jobs were running during the upgrade.

All fifteen stable-record fingerprint groups were preserved, including account
keys, users, Google identities, worker ownership/credentials, workspaces/members,
provider connections, application settings, agents, jobs, artifacts, checkpoints
and distributed records. The production environment file stayed byte-identical
with mode 600. No grant, model permission or provider credential was changed.

Deployment backup: `/opt/the-godfather/state/backups/20261023T162837-1808176`.
Backup checksums, PostgreSQL archive listing and compressed artifacts validated;
actual restoration was exercised in the isolated package gate, not on production.

The existing **0.9.0-rc.2** Windows x64, Mac Apple silicon and Mac Intel installers
and their download manifest were preserved byte-for-byte. No worker was rebuilt.

Public verification passed **94** normal-TLS HTTP checks, including anonymous and
foreign-origin denial for workspace model grants, provider connections and image
submission. All six installer downloads across both hostnames matched their
published hashes; both runtime catalogs matched. Edge verified desktop/light and
mobile/dark sign-in pages without overflow, mojibake or page errors. No real
Google account login, workspace grant or paid provider call was made by these
production checks.

## Changed files

- API inventory/permissions: `apps/api/src/godfather_api/workloads.py`.
- Images form and readiness: `apps/dashboard/src/components/workloads.tsx` and
  `apps/dashboard/src/components/image-readiness.tsx`.
- Regressions: `tests/integration/test_cloud_images.py`,
  `tests/dashboard-components.cjs` and `tests/e2e/image-workspace-access.cjs`.
- Setup, decision and release documentation: `docs/operations/cloud-images.md`,
  `docs/decisions/0027-cloud-image-providers.md`, `docs/history/phases.md`,
  `README.md` and this report. No dependency or database migration was added.

## Use after deployment

Refresh **Images**, choose your workspace and OpenAI or Google Gemini, then select
a model/computer. If marked **workspace permission required**, choose **Allow
selected model in workspace**. Enter your prompt, confirm both consents and choose
**Generate image**. Existing saved keys and worker settings do not need to be
re-entered for this workspace-permission correction.

Release evidence is under `.cache/image-workspace-fix/` and
`.cache/image-workspace-release-0.9.0-rc.3/`; server preservation evidence is under
`/opt/the-godfather/state/deployments/image-workspace-20261023-rc3/`.
