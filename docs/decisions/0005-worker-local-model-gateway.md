# ADR 0005: Worker-local model gateway and bounded inference snapshots

- Status: Accepted within authorized Phase 05
- Date: 2026-10-15

## Decision

Keep inference on explicitly opted-in outbound workers. Add the portable `godfather-model-gateway` Python package, with a small provider protocol and independently replaceable Ollama and OpenAI-compatible HTTP adapters. Reuse the already locked `httpx2` client as a runtime dependency for cancellable asynchronous HTTP; do not add a vendor SDK, another service, orchestration framework, or GPU-specific coordinator code.

Provider endpoints, environment-variable names for credentials, and operation declarations live in an owner-controlled worker configuration file. Credentials never enter registration or jobs. Ollama endpoints must be loopback. Other remote endpoints require certificate-validated HTTPS; proxies and redirects are disabled. Implement discovery and chat only: no model pulls, service installation, tools, embeddings, images, or external administration.

Extend worker v1 additively with `inference_protocol_version: 1` and a bounded deployment inventory. The existing `nodes.runtimes` JSONB snapshot durably owns this discovered inventory, just as it owns earlier installed-model advertisements. The schema-only `models`/`node_models` tables remain reserved definitions, not a second competing inventory. Discovery is replace-on-registration, tied to individually authenticated node identities. Existing columns also hold typed inference inputs, results, selected deployments and bounded partial snapshots. No DDL changes or new migration are necessary; existing migration and metadata checks remain required.

Model selection is part of typed execution requirements. A specific identifier never falls back silently. An omitted identifier requires explicit capabilities; configured capabilities count only when the submitter opts in. Select a matching deployment before creating an attempt, and persist that exact deployment on the attempt. Preserve scheduling locks, fair turns, owner consent, compatibility, reservations, concurrency and fencing. Known model memory estimates increase reservations; unknown requirements are not invented. Inference workers currently advertise one slot, matching their serial executor. Scaling per-node execution is an extension, not a false concurrency advertisement.

Persist small, bounded inference text in PostgreSQL: up to 32,768 characters, at most 512 append updates, each up to 4,096 characters. One attempt snapshot is updated rather than adding token/event rows. Final results use the same bounds. Larger outputs fail explicitly and need a separately designed artifact store before their limits can be increased. This trades bounded JSONB/WAL write amplification for no new storage infrastructure.

SSE reads fresh authenticated, workspace-authorized snapshots from PostgreSQL every 500 ms. It holds no transaction while waiting, works across API processes/restarts, and requires no Redis stream. Each subscription lasts at most 30 seconds; reconnect for the latest full snapshot. Every frame identifies its job, attempt and fence. A new attempt causes an explicit reset. Expired, cancelled and failed partials are suppressed even before scheduler maintenance. Clients replace snapshots and discard invalidated provisional output. SSE is not an exactly-once token replay log, and cannot retract text a client already consumed.

Cancellation and transport/ownership failures cancel the local inference task and close the provider HTTP stream. Closing a connection does not certify that a remote provider stopped computation or charging. Existing bounded at-least-once attempts apply; inference retries restart generation and may duplicate inference cost. No checkpoints, external side effects, failover restoration, or automatic model fallback are introduced.

## Verification and limits

See [Phase 05 operations](../operations/phase-05.md), [architecture](../architecture/model-gateway.md), and [inference protocol](../protocols/inference-v1.md). Mock providers give deterministic tests; a native worker and loopback fixture establish the HTTP/job path separately from physical inference. Real local Ollama remains an explicit acceptance gate when an installed model is available. Never infer physical GPU, macOS, remote-provider or cloud proof from mocks or CI configuration.
