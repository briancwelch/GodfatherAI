# ADR 0007: Cross-node recovery and local Command Center

- Status: Accepted for the explicitly combined Phase 07–08 milestone
- Date: 2026-10-15

## Decision

Extend the FastAPI modular monolith, existing scheduler, PostgreSQL claims, worker
v1 opt-in, model gateway and immutable local artifact store. No new orchestration
service, cloud storage, worker service installation or runtime dependency is needed.

Remove Phase 06's per-job same-node restriction. Retain its original node reference
for history. On lease/deadline expiry a workflow attempt becomes `INTERRUPTED`, its
lease is expired, its unfinished step is interrupted, and existing bounded retry
and exponential backoff return the job to the queue. Inactive ownership immediately
rejects old writes; reassignment increments the fence and creates a fresh attempt.
The expired process session cannot reacquire its own expired attempt. A different
compatible node or authenticated replacement process may restore the committed prefix.

Recovery reuses all matching, fairness, owner/workspace consent, model, resource,
platform, runtime and tool constraints. A queued job never reserves an incompatible
backup. Exact model requirements do not turn into a paid or different-model fallback.
The previous attempt UUID and resumed checkpoint version remain on each attempt
after completion. Durable recovery-assigned events identify both nodes and attempts.

Verify checkpoint identity, pinned workflow/agent versions and every referenced
committed output before assigning recovery. A corrupt/missing/inconsistent prefix
sets workflow `REVIEW_REQUIRED` with a safe error code while the job stays pending
and ineligible. There is no automatic fallback to an older or empty checkpoint, and
no automatic retry loop over damaged storage. The owner can cancel; repair/review
resolution is deliberate local administration rather than an insecure force-resume API.

Only existing bounded model/read-only tool steps can execute. Unsupported tools and
non-idempotent external operations remain rejected at definition validation. There
is no shell, arbitrary coding, filesystem replication or exactly-once external-write
claim. Synthetic coding-compatible workflows prove portable committed JSON state;
real Git/worktree coding remains Phase 11.

The Command Center uses real existing APIs and additional read projections in the
same API. Browser requests pass through a strictly allowlisted Next.js server route.
An existing administrator bearer credential is validated by the backend and held in
an eight-hour HttpOnly/SameSite=Strict cookie. Each request revalidates the individual
credential and existing permissions. No global administrator identity impersonates
all visitors. This local credential bridge is deliberately not production login or
Phase 09 full RBAC. Local HTTP cookies require loopback-only deployment; Host and
mutation Origin checks reject foreign origins and DNS rebinding targets.

Overview/table queries are bounded and expose limits/paging; counts use full scoped
PostgreSQL aggregates. Node directory health retains existing platform-admin scope;
private job/agent/event data requires workspace access. Node activity excludes jobs
outside the caller's workspaces. Polling is sequential every three seconds while
visible. Data freshness and unknown/simulated readings are explicit. Manual retries
require job ownership/workspace administration, a known safe failure, failed state
and fewer than eleven total attempts; prior attempts and checkpoints are preserved.

## Consequences

Database and the private artifact volume remain a single recovery/backup unit.
Coordinator/storage loss still requires later backup/restore work. Recovery cannot
restore uncommitted work, unsaved files, GPU memory or uncertain external effects.
Cross-platform simulated tests prove protocol/matching behavior, not physical
macOS/Linux/GPU inference. Both public hostnames remain unused. Phase 09, production
deployment, BYOK and WordPress writes remain outside this authorization.
