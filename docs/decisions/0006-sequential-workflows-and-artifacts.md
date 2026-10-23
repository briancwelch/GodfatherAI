# ADR 0006: Sequential read-only workflows and durable artifact checkpoints

- Status: Accepted within authorized Phase 06
- Date: 2026-10-15

## Decision

Reuse the existing scheduler, job lifecycle, model gateway, owner policies and fencing. Add a small portable `godfather-agent-runtime` package with sequential model/tool steps, a trusted read-only tool registry and explicit checkpoint callbacks. No LangGraph dependency is needed for this bounded sequence: PostgreSQL already owns attempts, transactions, leases and recovery decisions. There is no second scheduler, autonomous tool selector or visual engine.

Extend the existing agent schema with a stable agent key and enabled flag. Immutable version rows retain their own UUIDs and definitions; jobs reference an exact version row. Agent ownership/workspace and identity come from authenticated backend operations, never a worker. Legacy schema-only agent rows are retained, receive their existing UUID as stable key, and remain disabled until replaced by a supported definition. New versions are append-only, protected by expected-version checks and uniqueness constraints. Definitions have no node binding.

Migration `0004_agent_runtime` adds artifact metadata, workflow-run cursors, per-step attempt history and checkpoint-to-artifact references. PostgreSQL owns visibility, ownership, current cursor, checkpoint version and audit history. Intermediate results and complete checkpoint state are immutable JSON artifacts in a coordinator-owned persistent local volume. The local backend is behind a small storage protocol so a later backend can preserve references without putting large blobs in PostgreSQL. No cloud storage is configured.

Write and fsync immutable UUID-addressed artifact files before committing their database references. Under the existing credential/node/job locks, atomically commit the step record, output metadata, state artifact metadata, checkpoint version, job pointer and events. Recheck lease/deadline after storage I/O. A failed transaction can leave unreferenced files, but cannot expose an uncommitted checkpoint; cleanup/retention is deferred rather than deleting data automatically. Verify byte length and SHA-256 before serving/restoring artifacts. Storage/metadata mismatches fail visibly and never trigger a silent fresh start.

The initial tool `plan.describe@1` is deterministic, bounded, read-only and idempotent. Both agent permissions and independent node-owner tool/permission grants are checked by the backend and worker. The backend validates its input/output contract, including the expected deterministic output. No arbitrary code, shell, SQL, host paths, Git writes, MCP or external-account tool is accepted. The model can provide structured plan data but cannot select a tool or generate executable workflow instructions.

Recovery reuses bounded job retries and monotonic fencing. Resume the centrally committed prefix, not local memory. In Phase 06 a workflow run can recover only on its originally selected node, and recovery after lease/deadline expiry waits for a new authenticated process session. This is a per-job phase boundary, not a permanent agent/node binding. Compatible cross-node automatic reassignment is reserved for Phase 07. Uncommitted model/read-only steps may repeat; committed steps must not. Non-idempotent/uncertain external operations are unsupported and rejected, not automatically retried.

Existing synthetic/inference wire payloads stay unchanged when no workflow fields apply. A separate workflow v1 opt-in gates the new assignment. The extracted heartbeat/renewal/cancellation monitor is shared with inference. Internal structured model requests use native JSON-mode hints in the existing adapters and still require Pydantic output validation. Unsupported/malformed responses fail explicitly.

## Boundaries and verification

Phase 06 worker configuration permits loopback workflow providers only. The requested [BYOK design](../architecture/byok-plan.md) remains planning-only: no native frontier adapters, secret-store access, paid routing, spending grants or cost ledger are implemented here.

The native acceptance exercises three steps, interruption after checkpoint 1, actual API restart, same-node process replacement, no repeated committed steps and stale-report rejection. Deterministic tests cover rollback, corruption, permissions, cancellation, deadlines, versioning, serialization and the preserved scheduler guarantees. See [operations/evidence](../history/phases.md#phase-06) and [protocol](../protocols/agents-v1.md). Physical macOS/Linux/GPU proof, cross-node failover, production storage backups and public deployment remain separate gates.
