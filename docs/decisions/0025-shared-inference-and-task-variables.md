# Shared inference, Distributed Tasks and literal variables

Owner-authorized local implementation, 2026-10-22, including the later Nodes heartbeat indicator request. The original source scope excluded deployment, installer publication, engine installation, model downloads and billable inference. The owner subsequently explicitly authorized packaging and deployment; coordinator and all three installers are published as 0.8.0-rc.1. See the [deployment verification](../operations/shared-inference-deployment-2026-10-22.md). Engine installation, model downloads and billable inference remain separate.

## Decision

Distributed Jobs at `/distributed` means one text inference request to one owner-configured, private model engine that uses several devices. It supports three explicit topology declarations: `single_host` (multiple GPUs inside one computer), `local_network` (several computers on a private local network), and `wide_area` (several locations over private transport). Locations and member counts are data, never hardcoded scheduler logic. The external engine performs tensor or pipeline parallelism. This change does not implement GPU collectives or launch engines.

The existing parent/child workflow feature moves to **Distributed Tasks** at `/distributed-tasks`. Its PostgreSQL records, IDs, checkpoints and artifact references remain intact. `/api/v1/distributed/tasks` is canonical; the old `/api/v1/distributed/jobs` API remains a compatibility alias for task groups. It does not acquire shared-inference semantics. The new inference API is `/api/v1/shared-inference`.

Use the existing model gateway, worker transport, scheduler, attempts and fencing. Every member independently advertises the same bounded `SharedInferenceGroup` from owner-local configuration. The leader advertises a discovered OpenAI-compatible model bound to that group. Engine addresses and credentials stay local. The HTTP endpoint is restricted to leader loopback; any engine-to-engine transport must be separately owner-configured and private. Ordinary model discovery and scheduling exclude group-bound deployments.

No new database tables are necessary: declarations live in the existing versioned advertisement JSONB, the immutable selected topology in job requirements, and participating session identities in the durable attempt. Empty additive fields are omitted so ordinary old workers retain their wire format. Updated source workers advertise `task-variables-v1` only when workflow execution is enabled. Group setup requires the updated coordinator and participating workers.

## Scheduling and failure

### Explicit shared-model workspace access (2026-10-25)

Shared-model discovery must remain visible when the selected workspace has not
allowed the group's exact model identifier. Distributed Jobs lists these groups
as requiring workspace permission, while keeping every member's ownership,
contribution, workspace membership and active-group restrictions in force.
Discovery omits only the model-selection check; execution still checks the full
model allowlist and all existing scheduling and fencing rules.

A workspace owner or administrator can select **Allow in this workspace** for a
discovered shared model. `POST /api/v1/shared-inference/workspace-access` derives
the model identifier from the authorized leader's group declaration and matching
deployment. It locks the workspace, adds only that identifier to its existing
model allowlist, preserves tool restrictions, and audits an actual addition.
Repeated approval is idempotent. A platform administrator without workspace
administration cannot grant access or override node-owner restrictions.

Managed setups generate a distinct model alias for each setup. Allowing the
underlying Ollama model does not implicitly authorize every new shared topology;
recreated setups require explicit workspace approval. The ordinary Models page
continues to exclude shared deployments. No migration, worker update, model
download, inference request or automatic policy change is needed for this fix.

### Execution rules

A single scheduler transaction locks all available members under the existing PostgreSQL advisory scheduler lock. A group may claim only when every member is online, consenting, authorized in the workspace, and has no active reservations. The attempt reserves all concurrency slots on every member. Every preferred member retains first refusal for its own owner's compatible queued work. Active peer reservations remain effective even if the leader's row is temporarily locked by another request. One leader receives one ordinary inference assignment; peers contribute through the configured engine.

Every report rechecks group consent, member identities, current sessions, credentials, health, workspace restrictions and discovered leader model. Any member losing authorization, changing session or disconnecting fences late results; scheduler reconciliation fails the attempt. No automatic restart, fallback to a single node or paid cloud, or recovery of unsaved GPU state is promised. Group resource reservations describe Godfather scheduling; they cannot stop independent owner processes or force an external engine to unload GPU memory. Cancellation closes the leader HTTP request through existing worker cancellation; downstream engine cleanup remains runtime-dependent.

The topology and engine split are owner-attested configuration. Model discovery verifies availability, and single-host readiness additionally checks the advertised GPU count. It does not prove physical multi-host execution, effective network speed, model identity on every engine shard, or speedup. Those require separate hardware acceptance. Whole-host reservations deliberately favor correctness over concurrent inference throughput.

## Task references

Task instructions can reference earlier committed results with `{{tasks.task1.output}}`. The contract infers dependencies and validates a topologically ordered graph. Self, forward, missing, unknown, malformed or circular references fail. Explicit dependencies are still available. Independent tasks remain parallel; result-dependent tasks wait. A final synthesis transitively depends on all tasks.

Static variables include the authorized workspace ID/name, task group name/goal, current task key/name, selected agent ID/name/version and requested model identifier. Up to 32 custom text values use `{{vars.name}}`. References select context; they do not change a task's selected agent, model, workspace, node permissions or tool access. Outputs are integrity-checked artifact references from direct predecessors in the same task group. The coordinator snapshots metadata and populates references only after predecessor completion. Workers substitute once, quote output data and retain prompt bounds; no expression evaluation, recursive expansion, coordinator execution or arbitrary filesystem lookup occurs. Variables and dependent tasks currently require model-only agents. Expanded prompts exceeding the existing bound fail visibly rather than truncate evidence.

## Notifications and heartbeat

One global corner viewport renders compact icon/message/action/close rows. Red errors persist until dismissed; processing notifications remain until an observed terminal job state and have no duration timer. Eight-second success/information notices use the same layout. Processing bars use committed task/step counts or reported download-layer progress, otherwise remain indeterminate. A connection failure means unknown status, not failure or success. There is no automatic submission retry.

Only IDs and task-group flags are retained in tab session storage, scoped to the authenticated actor. Refresh and ordinary navigation restore tracking through authorized APIs; prompts, answers and names are not stored there. Sign-out clears notifications. API and local form errors retain their inline detail and also reach the corner. Dismissal hides a processing card while monitoring continues; a terminal state can notify again.

The small Nodes EKG uses the actual latest heartbeat timestamp. Its pulse moves through a 30-second display window and stops for stale/offline/unknown state. It is an indicator of receipt, not medical data, network latency, inferred historical beats or GPU utilization.
