# Worker protocol v1: registration and health

Phase 06 additionally defines optional workflow protocol/tool-grant fields and a gated workflow assignment in [agents/workflows v1](agents-v1.md). Existing registration, heartbeat, synthetic and inference messages remain valid; absent workflow fields are omitted from old assignment shapes. No new host permission is implied by registration or platform administration.

Phase 05 adds optional `inference_protocol_version` and bounded `model_deployments` registration fields, documented in [inference v1](inference-v1.md). Existing workers can omit both. Synthetic execution and inference have independent opt-ins; physical discovery is permitted for inference without granting host tools or shell access.

This document records the Phase 03 baseline. Phase 04 adds backward-compatible, opt-in [synthetic execution](jobs-v1.md), dependency inventory and owner/workspace contribution allowlists. Registration-only workers continue to operate and receive no jobs.

The canonical typed contract is `godfather_contracts` in `packages/shared-schemas`. This phase carries no tasks, execution permissions, leases, checkpoints or inference requests. A protocol change requires documented compatibility or migration; currently only integer version `1` is accepted. Authenticated unsupported versions receive HTTP 426 without modifying a node.

| Endpoint                                   | Credential             | Behavior                                                            |
| ------------------------------------------ | ---------------------- | ------------------------------------------------------------------- |
| `POST /api/v1/workers/register`            | Individual worker      | Registers its provisioned identity or reconnects the same process   |
| `POST /api/v1/workers/{node_id}/heartbeat` | That worker            | Updates resources, last heartbeat and connection health             |
| `GET /api/v1/nodes?limit=100&offset=0`     | Platform administrator | Lists registered nodes; limit 1â€“200                               |
| `GET /api/v1/nodes/{node_id}`              | Platform administrator | Inspects owner, health, platform, specialties, policy and telemetry |
| `POST /api/v1/nodes/{node_id}/control`     | Platform administrator | `action`: `drain`, `disable`, `enable`, or `revoke`                 |

Send exactly one `Authorization: Bearer TOKEN` header. Admin and worker credential kinds are deliberately separate. Tokens, request bodies and raw exceptions never enter API request logs or validation responses. Responses include the existing correlation header. Node lifecycle events carry the node, initiating actor when applicable, correlation ID, and safe transition details in PostgreSQL. Unchanged heartbeats update the node row without adding unbounded heartbeat audit rows.

The first successful registration emits `node.registered`. Re-registration emits
`node.reconnected` only when an allowed process-session replacement occurs or the
previous connection is suspect/offline, including receipt expiry before the next
health sweep. Online, same-session inventory refreshes still update the full
advertisement and heartbeat receipt without emitting reconnection events; this
also applies while the node is draining. Actual contribution changes retain their
`node.contribution_changed` audit event. Health transitions, credential-release
auditing, session fencing, lease timing and protocol v1 are unchanged. Existing
historical events are retained.

Registration combines the advertisement with `session_id` and `protocol_version`. Required fields are `os` (`windows`, `macos`, `linux`), `os_version`, `architecture` (`x86_64`, `arm64`, `x86`, `unknown`), and resources. Resources include `source` (`physical` or `simulated`), `cpu_name`, and positive `cpu_count`; memory/utilization and GPUs may be unknown. Optional fields declare primary/secondary capabilities, concurrency limit, scheduling policy, runtimes, installed models, toolchains, supported sandbox modes and warnings. Lists, strings and percentages are bounded. Capabilities must be unique across both specialties. No owner, node ID, credential, path, shell or tool grant is accepted in the registration body.

A heartbeat contains protocol version, the same process session UUID and a resource snapshot. Its telemetry source must match registration. Both worker endpoints return `node_id`, effective `state`, independent `connection_status` and the coordinator's heartbeat interval. Unknown fields and invalid resources receive 422. Missing/invalid/revoked credentials receive 401, disabled owners/nodes or wrong node scopes receive 403, duplicate live processes/stale sessions receive 409. Invalid bodies can receive 422 before authentication but never perform a management operation.

The coordinator uses its own UTC receive time; worker wall clocks cannot extend health. At elapsed 20 seconds the connection becomes suspect; at 30 it becomes offline. A heartbeat or permitted re-registration returns it online. Draining is retained while heartbeats continue, and health still expires when they stop. Disabled nodes reject registration and heartbeats. Enabling returns the current connection state without fabricating a heartbeat. Revocation permanently rejects a credential and disables a registered node.

The worker reconnects after network/5xx errors using the same process UUID and observable retry messages with exponential delay capped at 30 seconds. Authentication, compatibility and duplicate-session errors terminate the process with a safe status code. A new process using an existing credential must wait for the old process's offline deadline before registering. No heartbeat process recovers unsaved work or performs failover.
