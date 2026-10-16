# Phase 04: Durable job scheduler

## Scope and prerequisite

Phase 04 was explicitly authorized. Before editing, the existing real-PostgreSQL suite passed **87 tests** without skips. The full repository check passed: Python format/lint/strict typing, **54 Windows unit tests** (33 PostgreSQL tests separately executed), and frontend format/lint/type/build. The live four-process Phase 03 smoke also passed registration, fresh heartbeats, independent suspect/offline transitions, actual API/PostgreSQL restarts, ownership/identity persistence and credential cleanup. Prerequisite evidence: `.cache/phase03-runs/012ca5e68efc495eb419eaa7ab1217e9/result.json`. No prerequisite defect was found. The existing Phase 03 working-tree changes were preserved.

This phase adds PostgreSQL jobs/attempts/events, matching, fairness, leases/fences, cancellation, retries and opt-in synthetic workers. No real coding, inference, MCP, agents, dashboard management, checkpoint restoration or remote deployment is implemented. No service or dependency was added.

## Local startup

After the [existing setup](setup.md), from the repository root with the ignored local `.env`:

```text
uv sync --locked --all-packages
docker compose --profile tools build api migrate api-test
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Apply the additive `0003_durable_scheduler` migration explicitly. Existing data is retained. Readiness rejects a mismatched schema; startup never applies migrations. The active-attempt index refuses any inconsistent legacy duplicate active attempts instead of deleting records. Databases have no public/host ports.

Local API: **http://localhost:8000/api/v1**. Health: **http://localhost:8000/health/ready**. The unchanged disconnected shell remains **http://localhost:3000**; it does not display jobs or live metrics. Public names remain proposed and unused.

Defaults: 30-second execution leases, 10-second heartbeats, suspect/offline thresholds 20/30 seconds, and one-second maintenance. Configure `.env` `GODFATHER_EXECUTION_LEASE_SECONDS` and recreate the API. `GODFATHER_SCHEDULER_ENABLED=false` pauses assignment and execution recovery, retaining health monitoring. `health_monitor_enabled=False` is the internal deterministic-test switch disabling the combined maintenance task.

## Submit and inspect synthetic jobs

Provision a new synthetic administrator and two workers using [Phase 03](phase-03.md), or reuse your existing private development credential files. Do not print bearer tokens. Replace `OWNER_UUID`, `WORKSPACE_UUID` and `JOB_UUID` below with actual IDs:

```text
uv run --locked --all-packages python -m scripts.provision_local workspace --owner-id OWNER_UUID --name Scheduler-demo
uv run --locked --all-packages python -m scripts.jobs submit --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID --capability coding --count 100
uv run --locked --all-packages python -m scripts.jobs list --credential-file .cache/credentials/admin.json
uv run --locked --all-packages python -m scripts.jobs inspect --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.jobs events --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.jobs attempts --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.jobs cancel --credential-file .cache/credentials/admin.json --job-id JOB_UUID
```

Workspace provisioning is offline local database administration, not a public API. It creates a private workspace owned by the specified enabled user. No user/membership management UI is introduced. Use reviewed synthetic database fixtures for cross-owner membership testing until broader administration is authorized.

Open two terminals, each with its own provisioned worker credential:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LV-01.json --simulate LV-01 --execute-synthetic --concurrency 1
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LA-01.json --simulate LA-01 --execute-synthetic --concurrency 1
```

`--step-seconds 1` adds a bounded synthetic delay per step for observation. Workers renew leases and send heartbeats during delays. Without `--execute-synthetic`, Phase 03 registration/heartbeat-only behavior continues and no jobs are assigned. Physical discovery workers cannot opt into execution in this phase.

Dedicated nodes serve only their owner. Preferred nodes give their owner first refusal on compatible queued work and rank ahead of other eligible nodes for the owner's jobs. Shared nodes are normal eligible candidates. Primary specialties rank ahead of secondary specialties within the preference tier; compatible backups run when preferred capacity is unavailable. All nodes must be online, authenticated, enabled, fresh and compatible. Active reservations prevent oversubscribing declared CPU, memory and concurrency. GPU matching is conservative and never performs inference.

Across owners, the node owner must already have explicit workspace access. Its worker must then opt in with **both** `--allow-owner OWNER_UUID` and `--allow-workspace WORKSPACE_UUID`, and a non-dedicated policy. These can be repeated. Omit the flags to withdraw sharing on registration. Administrative health controls cannot supply them. Workspace public/shared flags do not grant membership. A job owner who loses workspace access cannot continue execution.

Fairness chooses the eligible user with fewest active assignments, then oldest persisted scheduling turn; priority and FIFO apply within that user's work. This is nonpreemptive admission fairness, not a resource-time quota. Incompatible head jobs do not block compatible jobs. See the [state machine, exact retry formula, endpoint contracts and fencing protocol](../protocols/jobs-v1.md) and [ADR 0004](../decisions/0004-durable-synthetic-scheduler.md).

## Repeatable acceptance

Run serially; the live smoke intentionally restarts the local PostgreSQL/API services. Never run database-reset integration tests concurrently with live acceptance.

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_job_scheduler
```

The PostgreSQL suite resets only the explicitly guarded `godfather_test` database in `environment=test` with `GODFATHER_RUN_INTEGRATION=1`; create it as documented in Phase 02. It verifies schema/migration metadata and round trips, validation, permission isolation, compatibility/reservations, primary/backup nodes, parallel scheduling/polling, expiry before sweeping, stale reports after reassignment/completion, cancellation races, retry bounds/backoff, API/pool recreation, node loss and persistent round-robin fairness. Its deterministic workload completes 100 jobs across two concurrent simulated worker sessions, with one active attempt per job.

The host smoke creates only new synthetic records and a private ignored `.cache/phase04-runs/RUN_UUID/` evidence directory. It submits 100 jobs before starting workers, actually restarts PostgreSQL/API, verifies all 100 remain pending, then launches two native worker processes. Ten inputs intentionally fail once, producing 110 attempts. It verifies terminal states and nonoverlapping attempt intervals and leaves an OS-incompatible job queued. It then stops the actual worker running another synthetic job, waits for lease expiry, and verifies retry on the surviving worker with a new fencing token. The handler runs from the beginning. Finally it cancels the incompatible probe, stops only its own child processes and revokes its three credentials, retaining rows/evidence. Failures also stop/revoke owned processes/credentials; synthetic jobs already created may remain queued or recoverable for inspection.

The CI OS matrix covers portable tests on Windows/macOS/Linux and Python 3.12/3.14. The serial Linux container job runs this live acceptance after Phase 03. Configured CI is not proof of an executed remote run.

## Validation and limits

Validated on 2026-10-15 using Windows x64/Python 3.14.8, Docker Desktop/WSL2 Linux amd64 and PostgreSQL 17.11:

| Check                               | Actual result                                                                                                                                             |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 03 prerequisite               | 87 PostgreSQL tests, full repository checks and four-process health/restart smoke passed before changes                                                   |
| Python format/lint/strict types     | Passed; 38 source files type checked                                                                                                                      |
| Windows database-free suite         | **84 passed**; 59 database cases deliberately skipped and separately executed against PostgreSQL                                                          |
| Complete PostgreSQL container suite | **143 passed**, no skips; includes 59 integration cases and the deterministic 100-job workload                                                            |
| Migrations                          | Additive upgrade, metadata comparison, idempotence and guarded disposable-database round trips passed; local application head is `0003_durable_scheduler` |
| Frontend                            | Prettier, ESLint, strict TypeScript and production build passed; dashboard source unchanged                                                               |
| Configuration/dependencies          | Compose validation, `uv pip check` and Git patch whitespace checks passed                                                                                 |
| Native two-process workload         | **100 completed jobs, 110 attempts, 48/52 completions across the two nodes, zero overlapping assignments**                                                |
| Actual API/PostgreSQL restarts      | All 100 pending jobs survived and later completed                                                                                                         |
| Real worker-process loss            | Stopped running LV Windows simulator; expired attempt failed; surviving LA macOS simulator completed fresh attempt with fencing token 2                   |
| Incompatible job                    | Linux-only job remained pending, then was explicitly cancelled during cleanup                                                                             |
| Cleanup and credential logging      | Both native processes stopped, all three run credentials revoked, all 102 synthetic jobs terminal, no run credentials in worker logs                      |

Final native acceptance evidence is `.cache/phase04-runs/425d327da6504a3385e226169a112a3a/result.json`, with individual worker logs beside it. An earlier complete live acceptance also passed in `4425d850f0e8418bb994c65c2c66d3ef`. Evidence/credentials stay ignored and excluded from Docker builds. Both runs recorded no overlapping execution attempts; the database unique index and concurrency tests additionally enforce active ownership. Checkpoint references stayed null. Local API and shell remain available on loopback. No unresolved local test failures remain. Remote CI is configured; its results must be checked separately on the pushed branch.

One initial regression test failed because new registration stored empty consent lists instead of the existing empty policy. Storage was corrected to preserve the old empty-policy representation, and the subsequent complete PostgreSQL suite passed. Later validation adds explicit exact-label dependencies, rollback and synthetic-worker cancellation tests.

No physical macOS/Linux worker, Metal/AMD/CUDA inference, actual coding, checkpoints, remote/Tailscale/TLS connectivity, public hosting, external integrations or browser authentication are established by simulation. The coordinator runs Linux containers locally on Windows. This scheduler is sized for the initial small cluster and scans queued jobs; no large-cluster throughput or time-based fairness claim is made. Full contributor/member RBAC and production security remain separately gated. Current endpoints are authenticated local development functionality only.

## Phase 04 files changed

| Area                       | Files                                                                                                                                                                                                         |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Control plane              | `apps/api/src/godfather_api/{app,config,models,nodes,provision,jobs,scheduler}.py`                                                                                                                            |
| Database                   | `infrastructure/migrations/versions/0003_durable_scheduler.py`                                                                                                                                                |
| Contracts                  | `packages/shared-schemas/src/godfather_contracts/{__init__,jobs}.py`                                                                                                                                          |
| Portable synthetic worker  | `packages/worker/src/godfather_worker/{__init__,cli,client,jobs,simulated}.py`                                                                                                                                |
| Simulation and local tools | `scripts/{provision_local,jobs,check_job_scheduler}.py`                                                                                                                                                       |
| Tests                      | `tests/test_scheduler.py`, `tests/integration/test_jobs.py`                                                                                                                                                   |
| Configuration/CI           | `.env.example`, `compose.yaml`, `.github/workflows/checks.yml`                                                                                                                                                |
| Documentation              | `README.md`, `docs/operations/{setup,phase-04}.md`, `docs/architecture/{compatibility,security-foundation}.md`, `docs/protocols/{worker-v1,jobs-v1}.md`, `docs/decisions/0004-durable-synthetic-scheduler.md` |

Repository rules added during this phase require dynamic users/nodes and a commit/push at phase completion. Scheduling uses persistent identities without geographic bindings. The phase is saved on `phase-04-durable-scheduler`, including the existing uncommitted Phase 03 foundation. The added rules in `AGENTS.md` are preserved; only trailing whitespace was removed.

Stop after Phase 04. The next recommended milestone is **Phase 05: local model inference**; do not begin without explicit approval.
