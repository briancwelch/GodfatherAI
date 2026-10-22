# Distributed Jobs: local implementation

Owner initially authorized local implementation on 2026-10-22. After local validation,
the owner explicitly authorized updated installers, coordinator deployment to the
existing VPS and GitHub synchronization. Release 0.6.0-rc.1 is being prepared through
the existing native packaging, backup and verification gates. Live billable inference,
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
Native installer updates were subsequently authorized and are being built through
the existing Windows and macOS packaging. Publishing them does not bypass local
update consent or change contributor permissions.

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
