# Agent runtime and durable workflows

Phase 11 adds one bounded coding step using an owner-approved repository snapshot
and worker-local container isolation. It reuses this runtime, checkpoints and
artifact store. See the [Phase 11 runbook](../operations/phase-11.md) for current
permissions and interruption behavior.

## Current Phase 07–08 extension

[ADR 0007](../decisions/0007-cross-node-recovery-and-local-command-center.md)
supersedes the same-node restriction in the historical Phase 06 sections below.
Compatible authorized nodes may now recover automatically, retaining attempt links
and checkpoint history. Interrupted workflow attempts use `INTERRUPTED`;
`REVIEW_REQUIRED` pauses an invalid artifact or pinned-version restoration. Every
committed output is integrity checked before reassignment. Bounded retry/backoff,
owner restrictions, workflow/worker v1 contracts and read-only tool limits remain.
The local Command Center consumes the same APIs. See [operations](../operations/phase-07-08.md).

Phase 06 executes a predefined sequential workflow through the existing scheduler and model gateway. It does not implement autonomous agents, arbitrary tools, multi-agent handoffs, cross-node failover, cloud/BYOK execution or full dashboard management. The [BYOK proposal](byok-plan.md) is design only.

## Portable definitions and identities

An agent has a stable `id` (stored as `agent_key`), an immutable `version_id` row UUID, an integer version, owner/workspace, enabled status and typed definition. Creating a version never mutates existing jobs or definitions. Definition management requires workspace administration; using an enabled agent requires workspace access. Global platform administration does not bypass private workspace access or node-owner tool grants. Existing schema-only agents remain retained but disabled/unsupported for execution.

The definition includes name/description, existing execution/model requirements, explicit allowed tools and permissions, workflow ID/version/steps, per-attempt timeout, bounded retry/backoff and mandatory `after_each_step` checkpoint policy. Model selection may specify capabilities or an exact identifier using the existing contract; no model name, machine, initial user, geography or provider is hardcoded into agent identity. Multiple configured agents can use the same workflow/tool kinds. Names/versions retain the existing workspace uniqueness rule.

Workflow identity is fully qualified by agent ID/version plus workflow ID/version. Each job pins that immutable definition and workspace. V1 has up to 32 uniquely identified steps, with optional references only to prior steps, and an aggregate 128 KiB UTF-8 definition limit. Supported kinds are `model` and `tool`. Supported output contracts are structured `plan`, bounded `text`, and the deterministic tool's `plan_summary`. Unknown tools/schemas and non-read-only permissions are refused. No `eval`, dynamic imports, executable expressions, arbitrary JSON-schema plugins or OS paths appear in definitions.

## Execution and transitions

```mermaid
sequenceDiagram
    participant Client
    participant API as API / PostgreSQL
    participant Store as Persistent artifact volume
    participant Worker
    participant Model as Local model gateway
    Client->>API: Create immutable agent version; submit workflow job
    API->>API: Existing fair/compatible fenced assignment
    Worker->>API: Poll definition, exact deployment and committed checkpoint state
    Worker->>API: Acknowledge/start; renew leases and heartbeat independently
    loop Each uncommitted predefined step
        Worker->>API: Step start with expected checkpoint version
        alt Model step
            Worker->>Model: Inference; validate text/JSON result
        else Allowed read-only tool
            Worker->>Worker: Validate grants/input; execute deterministic tool
        end
        Worker->>API: Fenced output, usage and expected checkpoint version
        API->>Store: Write/fsync immutable output and checkpoint state
        API->>API: Atomically commit cursor, checkpoint, step/artifact metadata and events
        API-->>Worker: New committed state/version
    end
    Worker->>API: Structured final result referencing final artifact
    Client->>API: Inspect status, steps, checkpoints and final output
```

The job state machine remains `PENDING`, `ASSIGNED`, `RUNNING`, `RETRY_WAIT`, `COMPLETED`, `FAILED`, `CANCELLED`. Separate workflow status is `READY`, `RUNNING`, `INTERRUPTED`, `COMPLETED`, `FAILED` or `CANCELLED`; its cursor/checkpoint version counts committed steps. Step-attempt history records `RUNNING`, `COMPLETED`, `INTERRUPTED`, `FAILED`, `CANCELLED`. A partial unique index prevents multiple completed records for the same job/step. Version and next-step checks reject skipped, reordered and contradictory writes. An identical last checkpoint retry from the same still-valid attempt is idempotent.

The existing worker loop executes one attempt at a time and advertises one slot. The original scheduler remains authoritative for claims, fairness, resources, specialties, owner policy, health, model availability and concurrency. Workflow admission additionally requires protocol opt-in, the enabled pinned agent and all declared tool/permission grants. The selected deployment is persisted on the attempt and used for its model steps. Node discovery, core execution and checkpoint JSON remain OS-independent.

The shared monitor renews existing leases and heartbeats while model inference or a fault-injection barrier is pending. Overall execution uses the existing assignment deadline; each step also has a timeout. Tools have an additional registry timeout. The backend rejects commits past step, lease or attempt deadlines, including a second lease/deadline check after artifact I/O. Cancellation wins over later completion, closes local inference tasks/HTTP streams and prevents new checkpoints. Disabling an agent prevents admission, starts and further step starts; an already running step may commit its valid checkpoint. Use job cancellation to stop current execution.

## Model and tool boundaries

The three-step demonstration generates a structured plan, passes it to `plan.describe@1`, and asks the model to summarize the validated result. Steps and tool references come from the versioned definition. Model text never chooses or invokes an arbitrary tool. The gateway uses an internal structured-request hint for JSON mode; the Phase 05 job payload does not gain extra fields. Ollama's JSON format and local OpenAI-compatible JSON-object mode are used where requested. Pydantic still validates the exact plan shape; unsupported JSON mode or invalid output produces a classified failure with no tool call/fallback.

Each tool publishes name/version, input/output schemas, required permission, timeout, read-only classification, idempotent retry safety and supported OS environments. Both sides check agent permission and worker-owner grants. Node health administrators cannot edit those grants. Step starts/completions and tool/model events contain identities and references, not sensitive input/output strings. The backend checks the deterministic tool's output against its declared input contract. No shell, arbitrary Python/SQL, files on contributor hosts, Git write, WordPress or other account access is exposed.

## Checkpoints and artifacts

`WorkflowState` v1 includes job, agent/version, workflow/version, active attempt/fence, cursor, completed step IDs, context/output artifact references, checkpoint version, historical model/tool references, recovery count/origin and last safe error code. It describes a validated committed prefix. Data consists only of portable JSON primitives/UUID strings; it never captures Python objects, connections, file handles, GPU memory or host-local paths. Completed step records reference their original attempts after recovery. Per-step identities and versioned artifact formats provide extension points for future graph/parallel/handoff states without moving execution state into process memory or replacing the durable tables.

PostgreSQL stores authoritative ownership, job/attempt relationships, cursor, step status/usage/error metadata and checkpoint/artifact references. Actual outputs and checkpoint JSON are in an immutable local artifact store with a per-artifact 256 KiB bound. Plan fields/items and text are independently bounded. The initial backend supports JSON artifacts needed by this phase; unrestricted binary/file ingestion and larger-output stores are future extensions. There are two artifacts per committed step: output and full checkpoint state. No per-token stream rows or unbounded database blobs are added.

Artifacts use server-generated UUID filenames under a configured versioned storage directory, SHA-256 checksums and recorded sizes. Clients cannot provide filesystem paths. Files and, where supported, directories are fsynced before database references commit. POSIX files/directories use 0600/0700; Windows requires an owner-private directory with appropriate inherited ACLs. Only database-referenced artifacts are served through authenticated workspace APIs or fenced worker reads. Storage failure rolls back all metadata/pointers/events for the step. Orphan files can remain after transaction failure; they are never served without metadata. Missing/corrupt artifacts fail closed with a visible 503 rather than restarting from empty state.

Compose mounts `artifacts-data` at `/var/lib/godfather/artifacts` on the API only. The API remains non-root with a read-only root filesystem. Tests use disposable `/tmp` storage; native development defaults to ignored `.cache/artifacts`. PostgreSQL plus the artifact volume form one recovery/backup unit. Keeping only database backups is insufficient. No volume deletion, retention purge, cloud object store or public file service is added.

## Interruption and recovery

On attempt expiry/failure, lifecycle events and unfinished step records are updated; committed checkpoints stay immutable. Bounded retries return the job to the existing queue. Phase 06 pins only the workflow job's recovery node after first assignment, and a lease/deadline interruption waits for a new authenticated session on that node. Compatible other nodes do not automatically claim it. The portable state/artifact API establishes the data path for Phase 07 without implementing cross-node failover now.

The replacement process polls a new attempt with a higher fence, restores and verifies the last checkpoint, and skips its completed steps. Only unfinished/uncommitted model or read-only tool work may repeat. A crash after the final checkpoint but before final completion resumes with zero remaining steps and publishes the existing final output reference. Every artifact read, step report and completion revalidates credentials, owner/workspace consent, current session, attempt, fence, lease and deadline. Stale workers cannot overwrite state or results, even before maintenance runs.

No supported tool has uncertain external side effects. Unsupported/non-idempotent operations are rejected at definition validation. A future side-effecting extension must add reconciliation/approval semantics before any automatic replay; this phase does not claim a paused-state implementation for operations it cannot execute. Local inference can repeat if uncommitted; cloud spending/reconciliation remains unimplemented under the separate BYOK proposal.

## Observability and limits

Events include workflow submitted/started/interrupted/resumed/completed/failed/cancelled, step start/complete/interrupted/failed/cancelled, model requested/completed, tool started/completed, and checkpoint committed. They carry job/workspace/user, workflow/agent versions, attempt/node, UTC timestamp, fence and correlation ID. Agent create/version/enable/disable changes are also audited. Successful model steps retain gateway usage metadata. Failed requests with unavailable usage do not invent token counts. Workspace APIs expose step history and references; no full Command Center is added.

No new third-party runtime dependency, production deployment, model download, frontier adapter, host service, automatic key transfer, cross-node failover, checkpoint retention cleanup or complete backup/restore system is introduced. Physical macOS/Linux/GPU results must be distinguished from Windows native, Linux containers, mocks and configured CI. See [protocol](../protocols/agents-v1.md) and [validation/runbook](../operations/phase-06.md).
