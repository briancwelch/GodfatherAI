# Distributed Jobs: implementation and deployment

Owner initially authorized local implementation on 2026-10-22. After local validation,
the owner explicitly authorized updated installers, coordinator deployment to the
existing VPS and GitHub synchronization. Release 0.6.0-rc.1 was built through
the existing native packaging, backup and verification gates and activated on the VPS. Live billable inference,
model downloads and changes to contributor-host permissions remain outside this work.

## Use

After the coordinator runs the new source and migration 0016_distributed_jobs,
open **Distributed Jobs** at `/distributed`. Workspace links retain their scope.
Select at least two permitted computers, enter one shared goal, and define parallel
tasks. Each task selects an enabled agent version (and therefore its permitted model)
and a computer. The optional backup checkbox permits any selected compatible node,
both initially and after a failure. Without it, that task waits for its single node.

Choose a model-only synthesis agent and a selected computer with distributed context
support. The final task waits until every parallel task has a durable final output,
then reads their integrity-checked artifacts and combines them. Results use the same
safe Markdown/artifact viewer as ordinary jobs. This first form supports model-only
analysis/planning tasks; it does not autonomously decompose the goal or merge code.
For research, supply evidence in the goal or existing approved workflow inputs; a
text model does not acquire browser access merely by joining a distributed job.

The API additionally accepts topologically ordered dependency graphs and independent
existing workflow types with their normal input/permission requirements, including
isolated coding tasks. Dependent tasks must be model-only. Repository patches remain
separate reviewable artifacts; no automatic apply, Git merge or deployment occurs.

Normal jobs and old workers retain their contracts. A synthesis worker must run the
updated source: `--execute-workflows` now advertises `distributed-context-v1`.
Consigliere 0.6.0-rc.1 Windows, Apple silicon and Intel Mac installers are published.
Use **File > Check for updates** on participating workers, or download the replacement
under **Nodes > Connect a computer**. The existing identity, projects and settings are
retained. Publishing installers does not bypass local update consent or change
contributor permissions.

## Limits and recovery

- 2-64 selected nodes, 2-16 tasks including the final task, and 128 KiB total request.
  Every selected node must occur in at least one task's eligibility pool.
- Combined goal/task instruction is limited to 4096 characters. Model prompts retain
  their existing 32768-character bound, including predecessor outputs. Oversized
  synthesis fails visibly; use smaller outputs or staged model-only synthesis tasks
  through the graph API. Evidence is never silently truncated.
- Model, platform, runtime, owner/workspace permission and resource matching all
  remain required. Offline or incompatible selected nodes leave work queued.
- Each child keeps its own durable checkpoints and attempt/fence history. Safe local
  model workflows retain bounded retries. Existing coding/paid no-replay policies
  stay in force. Unselected nodes never receive an automatic replacement assignment.
- A terminal child failure fails the parent and closes unfinished siblings. Inspect
  retained outputs before resubmitting; individual child manual retry is blocked.
- Cancel closes all unfinished children, fences late results and preserves committed
  outputs. It cannot reverse work already completed by a child.
- Contribution is recorded execution-time share, including failed/retried attempts.
  It is not GPU share or percent of the problem solved. Host CPU/GPU telemetry is
  separate and heartbeat-stamped; stale/offline host readings are unknown.

## API and implementation

`POST /api/v1/distributed/jobs` creates the parent and children atomically.
`GET /api/v1/distributed/jobs?workspace_id=...&offset=0&limit=25` lists authorized
parents. `GET /api/v1/distributed/jobs/{id}` returns graph/attempt contribution state.
`POST /api/v1/distributed/jobs/{id}/cancel` requires the owner or workspace admin.
`GET /api/v1/distributed/jobs/options?workspace_id=...` pages nodes and agent versions
in 25-item increments with `node_offset` and `agent_offset`. All browser requests
use the existing same-origin, authenticated session bridge and CSRF checks.

Main changes: `godfather_api/distributed.py`, scheduler permission/reconciliation
hooks, parent/task models and migration, bounded shared schemas, runtime dependency
reads, worker capability advertisement, the `/distributed` dashboard screen, and
integration/component/browser tests. See ADR 0023 and the design acceptance notes.

## Local validation

Tests use a separately named PostgreSQL container, a loopback-only ephemeral port,
`environment=test`, database `godfather_test`, synthetic identities/workers, and a
separate artifact directory. Existing local coordinator containers/data are preserved.
No real Google login, frontier credential or live inference endpoint is used.

Focused acceptance command, after configuring that explicitly disposable database:

```text
uv run --locked --all-packages pytest tests/integration/test_distributed.py tests/integration/test_database.py -q
npm test
npm run build
node tests/e2e/distributed-jobs.cjs
```

The browser test uses an isolated fixture API and local Edge. It verifies UI
interaction and presentation, not real remote hardware execution. PostgreSQL tests
exercise actual API/workers/scheduling/checkpoints with controlled model responses.
Physical cross-host models and distributed performance remain unverified.

Results:

- Complete regression run: **575 passed, 4 skipped** with real disposable PostgreSQL.
  Skips require optional pinned coding/data sandbox images or Windows symlink support.
- Final focused API/database/model rerun: **56 passed**, including all **17**
  distributed cases (parameterized invalid graphs included), separate installed
  models on concurrent nodes, non-admin explicit sharing, checkpoint failover,
  stale fencing, atomic invalid submission, cancellation and dependency isolation.
  This rerun follows the final participant-discovery and actual-model reporting changes.
- **31 dashboard component tests passed**. Repository Ruff formatting/lint, strict
  mypy, Prettier, ESLint, strict TypeScript and the Next.js production build passed.
- Isolated Edge acceptance passed selected-node task submission, synthesis backup
  selection, dependency edges, 90/10 measured-time bars, unknown offline telemetry,
  safe final-result rendering, light/dark themes, 390px layout, confirmed cancellation
  and stale API control disabling. No browser page errors were recorded.
- The migration metadata/idempotence test passed with actual PostgreSQL, including
  upgrade/downgrade/re-upgrade. No existing coordinator database was migrated.

Ignored local evidence: `.cache/distributed-full-tests.log`,
`.cache/distributed-focused-tests.log`, and `.cache/distributed-ui/` containing
`desktop.png`, `dark.png`, `narrow.png` and `result.json`.

No known serious unresolved implementation errors remain. Actual remote hardware,
installed worker binaries, GPU performance and billable provider execution were not
validated. The owner subsequently authorized committing/pushing this milestone and publishing
updated installers with the coordinator upgrade. Release results will be recorded
after activation; this local evidence alone does not claim remote acceptance.

## Published release and VPS activation

Coordinator and all three worker installers: **0.6.0-rc.1**, built from clean source
`eab6d21fb69b82bf37187bb2dbde192ba554b47a`. Source is committed and pushed to main.
The deployment report is saved in a subsequent documentation commit.

The [source CI run](https://github.com/briancwelch/GodfatherAI/actions/runs/39868688578)
passed all eight jobs. Its Linux container run completed **575 passed, 6 skipped**;
Windows, macOS, Linux and Python 3.12/3.14 checks, API/database restarts, four simulated
worker processes, the 100-job scheduler, lease expiry and checkpoint interruption /
recovery passed. Headless native-library and optional sandbox skips do not establish
physical hardware acceptance.

[Both native Mac jobs](https://github.com/briancwelch/GodfatherAI/actions/runs/39868728096)
passed app/DMG/checksum, native architecture/library, Tk/tray and HTTPS unapproved
pairing checks. Windows temporary install/reinstall, frozen Tk/tray and isolated
OS-store checks passed locally. These installers remain unsigned/ad-hoc signed;
recipient installation, physical models and GPU performance remain separate acceptance.

| Installer         | SHA-256                                                            |
| ----------------- | ------------------------------------------------------------------ |
| Windows x64       | `efc7e2c8d7b12a5413cdda4b3c3d337bed3b60391e41f1cfccf687feff378ccf` |
| Mac Apple silicon | `ee4dff4f22840ea7cfde8e6a3e6a7acadfe1dcdf6c00806935b3acf7e7e8d141` |
| Mac Intel         | `a4708083632dc47b578754d3de8034b850a50ba8a2fbc99d344a8c5421625bd1` |

Coordinator archive: `dist/godfather-0.6.0-rc.1-linux-amd64.tar.gz`, SHA-256
`cabdfc71e687bd76cdfd57b8aff6c0956e999b467f04bf6d8e14d4cc16202bcc`.
All ten disposable release gates passed, including immutable image identity and
content, production proxy configuration, shell syntax, fresh/repeat migrations,
private services, anonymous denial, all installer downloads through both hostnames,
actual database/artifact restore and persistence/restart.
Evidence: `.cache/release-tests/64e236007770/result.json`.

The transferred archive matched its trusted local hash before extraction. The normal
release installer took a paired backup, applied `0016_distributed_jobs` explicitly,
and activated `/opt/the-godfather/releases/godfather-0.6.0-rc.1-linux-amd64`.
A post-upgrade receipt helper needed a newline-escaping correction after successful
activation; only the receipt and read-only postflight were rerun, not the upgrade.

All five services are healthy. Only Caddy publishes host ports; PostgreSQL, Redis,
API and dashboard ports remain private. API metadata matches the exact source,
version and migration. All four workers reconnected online. No jobs were active at
upgrade or postflight, and verification created no distributed jobs.

The production environment remained byte-identical with mode 600. Stable record
fingerprints matched for 2 users (including profiles), 2 Google identities,
3 workspaces, 1 membership, 6 credentials, 4 node ownership/policy records, 12 jobs,
7 agents, 6 artifacts, 3 checkpoints, 3 provider connections and 1 encrypted account
key. No key was decrypted or contributor host reconfigured.

Paired backup: `/opt/the-godfather/state/backups/20261022T231216-1354615`.
SHA-256 checks, PostgreSQL dump listing and artifact gzip integrity passed.
Restore tests used disposable release data; production was not restored.
Previous releases are retained.

Server-side evidence: `/opt/the-godfather/state/deployments/distributed-20261022-rc1`.
Ignored local release/deployment evidence: `.cache/distributed-release-0.6.0-rc.1/`.

All **68 public HTTP checks passed** through normal DNS and verified TLS. All
three updated installers returned HTTP 200 with exact SHA-256 matches on both
hostnames (six full download/hash checks). Both runtime catalogs match the pinned
source catalog. Distributed Jobs redirects anonymous visitors to sign-in; its
list/options/detail/create/cancel bridge routes reject anonymous access and
foreign-origin writes. Private coordinator endpoints remain unavailable publicly.
These checks created no accounts, enrollments or jobs and used no real Google
session or provider key.

Open [Distributed Jobs](https://app.the-godfather.ai/distributed) after normal
sign-in. Update selected synthesis workers to **0.6.0-rc.1** before submitting;
ordinary jobs remain compatible with older workers. Actual recipient update and
physical multi-node/model execution remain owner acceptance tasks. No later
milestone was started.
