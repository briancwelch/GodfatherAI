# Agents, workflows and checkpoint protocol v1

All endpoints are under `/api/v1` and use existing administrator/individual-worker bearer credentials, backend workspace authorization, safe errors and correlation IDs. These are local-development APIs, not browser sessions or full Phase 09 RBAC. Definitions and jobs never carry provider keys, host paths or arbitrary tool code.

## Client API

| Method/path                                           | Behavior                                                                                  |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `POST /agents`                                        | Create version 1 with workspace and typed definition; workspace administration required   |
| `GET /agents?workspace_id=UUID&limit=100&offset=0`    | List supported versions in an authorized workspace; limit 1–200                           |
| `GET /agents/{agent_id}?version=N`                    | Inspect exact version, or latest if omitted                                               |
| `GET /agents/{agent_id}/versions?limit=100&offset=0`  | Paginated immutable version history                                                       |
| `POST /agents/{agent_id}/versions`                    | Append with `expected_version` and definition; a conflict returns 409                     |
| `POST /agents/{agent_id}/versions/{version}/control`  | `enable` or `disable`; definition remains immutable                                       |
| `GET /tools`                                          | Trusted tool contracts/schemas, not permission grants                                     |
| `POST /workflow/jobs`                                 | Submit an instruction using an enabled, exact agent version in the same workspace         |
| `GET /workflow/jobs/{job_id}`                         | Job plus workflow status/cursor/checkpoint state and references                           |
| `GET /workflow/jobs/{job_id}/steps`                   | Bounded step-attempt history, input/output references, usage/status/errors                |
| `GET /workflow/jobs/{job_id}/checkpoints`             | Checkpoint versions and artifact/agent/workflow metadata                                  |
| `GET /workflow/jobs/{job_id}/artifacts/{artifact_id}` | Authorized, integrity-verified JSON artifact content                                      |
| `GET /workflow/jobs/{job_id}/result`                  | Structured final reference/output only when completed; classified current error otherwise |
| `POST /jobs/{job_id}/cancel`                          | Existing durable cancellation, requiring job ownership or workspace administration        |
| `GET /jobs/{job_id}/attempts` and `/events`           | Existing attempt and paginated audit history                                              |

Agent IDs are stable across versions; `version_id` is the immutable database row referenced by a job. The backend derives owner and initial identities. `enabled` control is per version. Definition fields are `name`, `description`, `requirements`, `allowed_tools`, `permissions`, `workflow`, `timeout_seconds`, `retry`, `checkpoint_policy`, `enabled`. Workflow contains its own UUID/version and 1–32 unique sequential steps. Steps have ID, model/tool kind, instruction, output schema, optional prior `input_step`, optional versioned tool, timeout and typed model parameters. All future unknown execution fields are rejected. See [architecture](../architecture/agent-runtime.md) and `godfather_contracts.agents` for exact bounds.

Creating a version uses `{expected_version, definition}`. Existing submitted jobs keep the old version. Unsupported legacy schema-only definitions remain disabled and are omitted from executable lists; inspecting/enabling them returns a safe 409. Existing unique workspace/name/version and new stable-key/version constraints reject ambiguous duplicates.

Workflow submission example:

```json
{
  "workspace_id": "00000000-0000-0000-0000-000000000001",
  "agent_id": "00000000-0000-0000-0000-000000000002",
  "agent_version": 1,
  "input": {
    "instruction": "Prepare a short plan for inspecting a synthetic report."
  },
  "priority": 0
}
```

Use actual provisioned IDs. Timeout, retries, model/resource requirements and tool policies come from the pinned agent, not a submitter override. General `/jobs` submission does not accept arbitrary workflow payloads; use the dedicated route. Final `WorkflowResult` includes workflow/agent identity and version, checkpoint version, completed step IDs and final output artifact reference. No blob or local path is stored in the job result.

## Worker extension and grants

Registration adds optional `workflow_protocol_version: 1`, `worker_tools: [{name, version}]` and `tool_permissions`. Both grants are node-owner-controlled through the individual worker credential. Workflow workers also opt into the existing inference protocol and advertise model deployments. Model matching plus tool/reference/permission matching is required. Old workers omit these fields and receive no workflow jobs.

The existing poll endpoint returns an optional workflow bundle containing the pinned `AgentView` and current portable `WorkflowState`, plus the selected model deployment. Synthetic/inference assignments omit the workflow field. Empty tool requirements are omitted from their payloads so strict older workers remain valid. Existing ack/start/renew/progress/fail/cancel/complete reports retain all fencing guarantees; `complete` additionally accepts a validated workflow result only after all declared steps commit.

| Method/path                                               | Body and behavior                                                                                                              |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `POST /workers/{node_id}/jobs/{job_id}/workflow/report`   | Fenced identity plus `step_start` or `checkpoint`, step ID, expected checkpoint version, optional typed output and model usage |
| `POST /workers/{node_id}/jobs/{job_id}/workflow/artifact` | Fenced identity plus artifact reference; reads only an artifact belonging to this job/workspace                                |

Fenced identity contains session UUID, attempt UUID, monotonically increasing fence and job protocol version 1. Every operation locks/revalidates current ownership, node/workspace permission, active state, lease and deadline. Step reports require a running, non-cancelled workflow and the next uncommitted step. Checkpoints additionally require a started step, valid schema, expected version, valid tool grants/output and model usage only on model steps. A second lease/deadline check follows artifact persistence. Identical duplicate checkpoint writes are idempotent only for the same valid attempt and last committed output. Changed/reordered/stale writes are rejected.

Initial output schemas are `plan` (`title`, 1–16 bounded item strings), `plan_summary` (`title`, item count, deterministic outline), and `text` (up to 8,192 characters). Artifact references contain UUID, SHA-256 checksum, byte length and format version 1. Each immutable JSON artifact is at most 262,144 UTF-8 bytes. Checkpoint files contain only primitive structured state and references; no executable serialization or worker-local paths exist.

Missing/wrong/revoked credentials return 401; unsupported permissions/disabled starts 403; inaccessible resources 404; stale ownership/version/state 409; invalid schema/definition 422; expired step deadline 408; unavailable/corrupt artifact storage 503; unsupported execution protocols 426. Worker errors add `workflow_validation`, `tool_permission`, `artifact_unavailable`, `step_timeout` to safe existing codes. Step timeout and existing transient/provider failures may use bounded retries; malformed workflow/tool data is final. No raw exception/provider body is persisted.

## Recovery and events

Checkpoint metadata, cursor, completed step record, artifact references, job pointer and events commit together. Restore validates checksum, byte length, format, job/agent/workflow identity and the committed prefix. An expired or replaced worker cannot publish a checkpoint, read artifacts or complete a job. A current authorized attempt may read earlier committed output for its own job.

Phase 06 retries use the original selected node; lease/deadline recovery requires a new authenticated process session after health expiry. A compatible other node stays ineligible. A new attempt receives the last committed prefix with current attempt/fence and recovery metadata. Completed steps keep original attempt references and are skipped. The final checkpoint can be completed without rerunning model/tool steps. Cross-node automatic failover is not included.

Workflow/model/tool/checkpoint events include agent/workflow versions, step IDs where applicable, safe codes/refs, actor, job/workspace/attempt/node, UTC time, fence and correlation. Sensitive instructions and tool/model outputs stay in authorized job/artifact data, never event text or logs. The future Command Center can consume these endpoints/events; no UI controls are added in this phase.
