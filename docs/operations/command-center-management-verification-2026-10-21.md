# Command Center management deployment - 2026-10-21

**Coordinator 0.4.1-rc.2 is deployed** at [Command Center](https://app.the-godfather.ai).
The owner authorized the maintenance update and existing VPS deployment. The
later requests added the workspace archive popup and animated progress. Phase 13
has not begun. Consigliere workers and installers remain **0.4.0-rc.3** and were
not rebuilt, installed, reconfigured or restarted by this task.

## Application revision and artifacts

Source: `842b122c7301e7b2c79e7e86b7134f201195c4fe`, committed and pushed to main
before building. The initial feature commit was `92c1212`; the follow-up protects
completed source jobs while a dependent result action is unfinished. Candidate
0.4.1-rc.1 was staged but never activated. The final immutable archive is:

- `dist/godfather-0.4.1-rc.2-linux-amd64.tar.gz`
- SHA-256 `572362c318747cbeb14cbc7389f45b30f2a6f098a24a191e2d23be16755846fd`
- Additive migration `0013_command_center_deletion`
- Build metadata `2026-10-22T01:10:01.287346+00:00` (UTC)

Only API/dashboard application code, an additive coordinator migration, tests
and documentation changed. Worker packages, wire schemas and installer sources
have no changes. Existing worker downloads were passed to the established
release packager and compared byte-for-byte with the prior production release.

## Delivered behavior and files

- `administration.py`, API models and listing/access helpers: authenticated,
  atomic logical deletion of up to 100 selected workspaces, jobs or agents.
  Workspaces require ownership; job control and agent management retain workspace
  permissions. All agent versions are deleted together. Unfinished jobs and
  dependent apply actions block deletion. Attempts, checkpoints, artifacts,
  billing history and scoped audit records retain their foreign keys.
- `workspace_archive.py`: owner-only bounded ZIP export of configuration,
  memberships, agent versions, jobs, attempts, workflows, checkpoints, verified
  artifacts and scoped events. Manifest includes counts and SHA-256 values.
  Account secrets, private provider/billing records and worker-local data are
  excluded. Limits: 128 MiB uncompressed and 10,000 records per entity/workspace.
- `bulk-table.tsx`, `workspace-delete.tsx`, `operational.tsx` and dashboard styles:
  selected-row operations over asynchronous requests; the workspace dialog has
  archive preparation, measured download progress, explicit skip, cancellation
  and a separate delete step. Indeterminate preparation never invents a percent;
  reduced-motion preferences are respected. Jobs/agents use simple confirmation.
- `administration.tsx`: exact selected-user workspace-role lookup, current
  platform-role/account/permission display for platform administrators, preserved
  checked roles when adding access and normal session revocation on role updates.
  Stale requests cannot replace another selected user's editor. Owner access
  remains inherent; node-owner restrictions remain independent.
- Operational/admin views: pagination at both ends of existing paginated lists;
  form-contained pagers use non-submitting buttons. UI, API bridge allowlists,
  PostgreSQL/browser tests, the [operator guide](command-center-management.md)
  and [ADR 0020](../decisions/0020-command-center-deletion-and-archives.md) record
  the behavior and retention/authorization boundaries.

## Executed local checks

- Final disposable PostgreSQL suite: **520 passed, 3 skipped**. The skips are two
  opt-in coding-container tests and one opt-in data sandbox test, unrelated to
  this coordinator maintenance update. No production fixtures were used.
- Final focused management suite: **8 passed**, including atomic refusal,
  cross-user/worker/anonymous denial, idempotent retries, all agent versions,
  retained artifacts/history, exact membership beyond one member page, archive
  checksums, corrupt/missing artifact and size failure, concurrent submission vs
  workspace deletion, and the dependent result-action guard.
- Ruff format/lint and strict mypy (**156 files**) passed. Prettier, ESLint,
  TypeScript, production dashboard build and **21 component tests** passed.
- Isolated Edge browser acceptance passed AJAX jobs/agent deletion without page
  navigation, top/bottom controls, exact membership loading beyond the first
  page, additive platform roles, ignored stale-user responses, archive progress
  and download, failed archive with no deletion and explicit skip. Desktop
  1440px and mobile 390px layouts passed and were visually inspected. These use
  loopback fixtures and do not establish private-account production acceptance.
- Saved final coordinator images passed configuration/Caddy and shell syntax,
  fresh/repeated migrations, no seeded identities, private service health,
  anonymous denial, existing installer downloads, restart persistence and an
  actual paired database/artifact restore in an isolated local release project.
  Evidence: `.cache/release-tests/5e3a84c49a83/result.json`.
- [Final source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39704092684):
  **All eight jobs passed**, covering Windows/macOS/Linux Python and dashboard
  checks, Python 3.12/3.14, real PostgreSQL integration, API/database restart and
  outage recovery, four-worker health, the durable 100-job scheduler, loopback
  inference and interrupted-workflow checkpoint recovery. The earlier run was
  cancelled when the source-job guard commit superseded it.

## Production verification

The existing VPS now resolves `/opt/the-godfather/state/current` to
`releases/godfather-0.4.1-rc.2-linux-amd64`. API metadata reports the exact source
above and schema `0013_command_center_deletion`. API, dashboard, Caddy, PostgreSQL
and Redis are healthy. PostgreSQL/Redis retain private ports and the pinned
PostgreSQL image identity is unchanged.

Pre/post fingerprints match for **2 users, 2 Google identities, 2 workspaces,
3 credentials, 1 node ownership/policy, 8 jobs, 3 agents, 4 artifacts,
2 checkpoints, 2 provider connections and 1 encrypted account-provider key**.
Memberships remain empty. The added nullable deletion fields are excluded from
legacy row hashes; existing content is preserved. No real workspace, job or agent
was deleted, archived or edited as a production acceptance fixture.

The private environment, including proxy and vault keys, is byte-identical and
mode 600. No DNS, firewall, Google Cloud, model or account configuration changed.
The existing worker is online; no worker installation or real job was triggered.
Paired pre-upgrade backup:
`/opt/the-godfather/state/backups/20261022T011513-787245`.
Its checksums, PostgreSQL dump listing and artifact gzip validated. Production
restore was not performed; actual restore was tested in the disposable release.
Evidence: `.cache/command-center-management/upgrade-rc2.log` and
`postflight-rc2.log`.

Normal DNS and verified TLS return HTTP 200 for the app. Live download and
anonymous/foreign-origin checks are recorded in
`.cache/command-center-management/public-result.json`. The served worker manifest
and installer hashes remain the prior 0.4.0-rc.3 values.

## Limits and remaining acceptance

Logical deletion removes active access; it does not purge retained execution or
provider history. Exports are portable JSON/envelope archives for safekeeping and
review; automatic import is not implemented. The browser receiving an archive is
not proof that the user saved it; the dialog asks the user to verify the ZIP.

Real signed-in archive/deletion/role acceptance remains an owner action. This
turn did not access a private Google account or delete customer data to create
live acceptance evidence. Existing optional physical/GPU/container acceptance
boundaries are unchanged. See the operator guide for exact use.
