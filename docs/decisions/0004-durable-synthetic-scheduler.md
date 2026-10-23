# ADR 0004: Durable synthetic scheduler in the control plane

- Status: Accepted within authorized Phase 04
- Date: 2026-10-15

## Decision

Keep scheduling in the existing FastAPI modular monolith. Its maintenance loop sweeps health and then schedules every configured health scan interval. All API processes may run maintenance. A PostgreSQL transaction advisory try-lock (`7040401`) serializes scheduling decisions without another service. HTTP polling only delivers already assigned work. Redis is unused.

Use PostgreSQL row locks with `SKIP LOCKED` on candidate nodes and jobs. Worker mutations serialize on credential, node and job. Maintenance locks jobs and never waits for node locks; candidate node selection skips them. The scheduler never locks credentials. Cancellation locks the job. A partial unique index on active attempts independently enforces one `ASSIGNED`/`RUNNING` attempt per job. Node row locks protect concurrency and aggregate reservations. Assignment, attempt, fairness turn and audit changes commit together before any delivery.

Store assignment on the job, the current attempt number and monotonically increasing per-job fencing token, the attempt's worker session, lease expiry, assignment deadline, acknowledgements, classified errors and results. The current attempt UUID is resolved through the durable unique `(job_id, number)` relation. A new attempt increments both attempt count and fencing token. Every report checks all identities, active states, session, permission and unexpired lease/deadline under locks, even before a maintenance sweep. Terminal attempts cannot update results. Expiry and retry decisions are durable.

Persist per-user scheduling turns. Choose an eligible user's next job by least active assignments, oldest dispatch turn, then that user's priority and submission order. Priority cannot bypass user fairness. Preferred nodes offer their owner first refusal on compatible pending work; dedicated nodes serve only their owner, while shared nodes compete normally. Primary specialties rank ahead of secondary specialties within the preference tier. This is cooperative, nonpreemptive fairness, with no wall-clock quota guarantee. Incompatible jobs cannot block a compatible job behind them. This small-cluster scheduler scans queued work; batching/index tuning is deferred until measured need.

Use typed requirements for OS, architecture, capabilities, model/runtime pairs, versioned dependency labels, toolchains, sandbox modes, CPU, RAM and GPU backend/memory. Reserve resource amounts for active assignments. RAM matching uses both known available memory and capacity less reservations. GPU memory conservatively uses the largest matching device less all active GPU reservations; it never invents dedicated Apple GPU memory. Unknown required resources fail closed. CPU percent is telemetry; admission reserves declared logical CPU capacity, without promising CPU isolation or performance. Simulations establish matching only, not physical model availability or GPU execution.

## Early permission boundary

Retain individually authenticated worker credentials and administrator API credentials. No browser login or full RBAC is introduced. Both founding administrators have the same application role, but job API access requires workspace ownership or explicit membership. A public/shared workspace flag does not automatically grant access. Cancellation requires job ownership or workspace administration. Submission always uses the authenticated actor as owner; clients cannot nominate another user.

The node owner must also have workspace access. Cross-owner execution additionally requires both explicit owner and workspace UUID allowlists advertised by that individually authenticated worker, and a non-dedicated policy. Defaults are private. Administrative health controls cannot change sharing consent. Consent changes are audited; revocation is checked on delivery and every report. This grants synthetic execution only, never shell, files, repositories or tools. Re-registering without allowlists withdraws sharing consent. Local offline provisioning has existing database authority and is not a remotely callable permission bypass.

## Scope and compatibility

Registration and health protocol v1 remain valid. An additive job protocol v1 opt-in is required for assignment. Older registration-only workers receive no jobs. Only explicitly simulated workers and `synthetic.echo`/`synthetic.fail` inputs are executable. No arbitrary code, subprocess, SQL, model or MCP job payload exists. Retryable synthetic failures and lease/deadline expiry may retry from the beginning with bounded exponential backoff. No checkpoint is restored. The nullable checkpoint reference reserves the schema contract; this phase exposes no checkpoint writes. Future non-idempotent handlers require separate approvals/idempotency/reconciliation design.

Migration `0003_durable_scheduler` is additive. Existing schema-only job/attempt/checkpoint rows remain; only supported synthetic job types can be scheduled. The active-attempt index will explicitly refuse an inconsistent pre-existing database rather than silently deleting attempts. Downgrades are tested only against the guarded disposable test database. No dependencies or services were added.

## Verification

See [Phase 04 operations and evidence](../history/phases.md#phase-04), the [job protocol](../protocols/jobs-v1.md), deterministic unit/integration tests, and `scripts/check_job_scheduler.py`. CI is configured for cross-platform core tests and serial Linux PostgreSQL/native-worker acceptance; configured CI does not prove a remote run.
