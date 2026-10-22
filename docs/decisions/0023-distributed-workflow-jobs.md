# Distributed workflow jobs

Accepted for owner-authorized local implementation, 2026-10-22. The owner subsequently
authorized installer updates, VPS coordinator deployment and GitHub synchronization.
Real contributor jobs and paid inference still require their normal explicit consent.

A distributed job is a durable PostgreSQL parent with a bounded directed acyclic
graph of ordinary workflow jobs. Independent children run simultaneously on their
explicitly selected eligible nodes. The existing scheduler remains responsible for
resource matching, fairness, owner consent, model selection, leases, fencing,
checkpoint recovery and attempts. No separate queue, service or orchestrator is added.

Migration 0016 adds parent metadata and child membership/dependencies. It does not
rewrite existing jobs, identities, agents, connections or checkpoints. The parent is
never assigned to a worker. All child jobs are created atomically with the parent;
unreleased dependencies prevent scheduling, delivery and reports through the common
permission predicate. Scheduler reconciliation releases a child exactly once after
its direct predecessors complete. Its immutable input then contains only validated
references to those predecessors' final artifacts, rather than copying large model
outputs into PostgreSQL. A final task must transitively depend on all other tasks.

New workflow workers advertise distributed-context-v1. Only dependent children
require it; their new dependency_outputs input field is omitted when empty so old
workers retain ordinary workflow compatibility. Worker reads reuse the existing
fenced artifact API. The coordinator authorizes each exact reference against that
child's committed direct predecessors, same workspace and parent. Clients cannot
supply dependency references through normal workflow submission. Reads verify stored
checksums. Dependencies enter model prompts as data, with the existing 32768-character
limit; oversized prompts fail visibly rather than silently discard evidence.

Dependent agents are model-only, so predecessor output cannot choose a host tool or
apply a patch. Independent children can use existing supported workflow types and
permissions through the API, including isolated coding workflows with owner-approved
repository inputs. Coding outputs remain reviewable patches; this feature does not
merge or apply them. The initial browser form uses model-only agents for independent
analysis/planning and synthesis. This is task parallelism, not model/VRAM sharding.

Selection is an eligibility pool, not a promise every node will receive a task.
No unselected replacement may claim a child. Each selected task node must already
have workspace and contribution consent; scheduling/reporting recheck it. Model,
provider, paid-use and egress policies retain their existing checks. Paid and coding
replay restrictions are unchanged. No credential is copied into graph state.

Parent cancellation immediately closes unfinished attempts and rejects their later
writes, retaining committed artifacts. A permanently failed/cancelled child fails
the parent and closes unfinished siblings. Safely retryable child failures first use
their existing bounded automatic retry policy/checkpoints. Independent manual child
retries are refused; after terminal failure inspect results before submitting a new
group. Cancellation cannot undo an external effect already performed by an otherwise
authorized child workflow.

Reconciliation uses the scheduler advisory lock and skips locked parents/children;
parent cancellation locks children by ID. HTTP reporting never needs a parent row
lock, preserving existing credential/node/job lock ordering. A process restart needs
no in-memory graph reconstruction beyond loading durable rows.

The screen displays dependency edges, models, node connectivity, attempts and
checkpoint counts. Contribution bars divide recorded attempt execution seconds across
nodes, including retries. They do not measure answer quality, completion fraction,
CPU/GPU allocation or reserved capacity. Whole-host utilization is separate,
heartbeat-stamped, and absent when stale/offline. Empty time measurements stay unknown.
