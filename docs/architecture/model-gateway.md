# Model gateway architecture

Phase 11 extends this gateway with native OpenAI Responses and Anthropic Messages
adapters, independent provider connections, worker-local OS secret storage and
durable billing reservations. See the [current runbook](../operations/phase-11.md).
The original Phase 05 implementation and acceptance boundaries below are historical.

Phase 05 adds text inference only. The coordinator remains the existing FastAPI/SQLAlchemy modular monolith with PostgreSQL authority. Workers make all provider calls, and initiate all coordinator connections outbound. No inference endpoint is exposed by The Godfather on a worker.

```mermaid
sequenceDiagram
    participant Client
    participant API as Authenticated API / PostgreSQL
    participant Worker as Opted-in worker
    participant Provider as Worker-local configured provider
    Worker->>Provider: Discover installed models and metadata
    Worker->>API: Register identity/session and deployment inventory
    Client->>API: Submit inference requirements and bounded prompt
    API->>API: Permission/resource matching; transactional assignment and fence
    Worker->>API: Poll, acknowledge, start
    API-->>Worker: Job, attempt, fence, exact deployment and deadline
    Worker->>Provider: Chat with configurable parameters
    Provider-->>Worker: NDJSON / SSE / JSON
    Worker->>API: Bounded output batches; independent renewals and heartbeats
    API-->>Client: Attempt-tagged SSE snapshots
    Worker->>API: Fenced final result and usage
    Client->>API: Retrieve durable result / metrics
```

## Provider interface

`godfather_model_gateway.Provider` exposes asynchronous `discover() -> list[ModelDeployment]`, `infer(model, request) -> AsyncGenerator[Chunk]`, and `close()`. `generate()` adds the shared total deadline, text limit, cancellation cleanup and metrics. Provider adapters can be replaced through `create_provider`; tests inject transports or a protocol implementation. A future provider kind requires a reviewed versioned contract/factory extension. Adding models, provider instances of supported kinds, users, or nodes requires configuration/registration only.

`ProviderConfig` supplies an owner-defined alias, provider kind, endpoint, optional credential environment-variable name, timeout, declared capabilities and explicitly enabled OpenAI-compatible operations. Jobs cannot supply endpoints, credential names, raw provider parameters, shell commands or tools. Parameters are a typed allowlist: temperature, top-p, maximum output tokens and optional seed.

Ollama uses installed-model `/api/tags`, per-model `/api/show`, and `/api/chat`. Provider-reported `completion` permits chat/stream operations. Digest, context metadata and on-disk size are retained when returned. Disk size is not a RAM/VRAM estimate. OpenAI-compatible APIs use `<configured-base>/models` and `chat/completions`; configure a base including `/v1` where required. Listing an identifier does not certify chat or streaming support, so those operations require owner declarations. No active inference probe is performed during discovery.

Adapters normalize content, completion, counts, finish reason and errors. They bound HTTP bodies/lines, reject malformed/truncated responses, redirects, tools and reported model substitution, and never propagate provider exception/body text. Nonstandard compatible APIs may need another adapter: providers that reject `max_tokens`, seed, or streaming usage options are not silently retried with altered requests.

## Discovery, trust and scheduling

The authenticated worker's inventory is stored atomically in its durable runtime snapshot. `provider_id + identifier` is unique per node. Multiple aliases/models per node and identical identifiers across nodes are supported. The server derives node/owner identity from credentials; the payload cannot choose it. Inventory contains no endpoint or key. Registration-only and synthetic workers remain valid and cannot receive inference unless independently opted in.

At startup and between jobs at approximately 30-second intervals, the CLI rediscovers providers and re-registers the same session. Providers are probed concurrently with five-second discovery deadlines, so a failed collection cannot exceed the default heartbeat/offline budget. Failed discovery emits a safe code and withdraws that provider's old deployments. Inventory is bounded to eight provider configurations and 128 combined deployments. Refresh is deferred during an active attempt; heartbeats and renewals continue independently. Availability is a snapshot, not a guarantee against a model disappearing immediately after discovery.

`verified_capabilities` means metadata returned by the provider, not independent benchmark or security certification. `declared_capabilities` and OpenAI-compatible operation declarations are owner configuration. The source is explicit. Context windows describe reported model metadata, not a guarantee of effective loaded runtime context. RAM/VRAM estimates are nullable and labeled estimates. The initial adapters leave them unknown; a provider extension can report reliable estimates. Hardware/backend detection remains separate from proof of actual inference.

Scheduling requires the inference protocol opt-in, an available deployment with the exact requested identifier/provider if specified, requested capabilities/operations/context, and all existing OS/architecture/runtime/dependency/toolchain/resource requirements. Existing workspace access, node-owner cross-owner allowlists, dedicated/preferred/shared policies, specialty ranking, fresh health, resource reservations and concurrency still apply. Current CPU load breaks otherwise equal candidate ties; it is telemetry, not a CPU isolation guarantee. Known model memory estimates raise reservations. Capability-based selection is explicit, deterministic by provider alias/model identifier within an eligible node, and has no quality ranking or hidden fallback.

## Execution, storage and observability

The selected deployment, attempt UUID, monotonically increasing fence and deadline are assigned transactionally. Workers acknowledge/start before executing. Renewals, heartbeats and cancellation checks continue while HTTP inference blocks. Output and completion use the existing credential/node/job locks and verify the current session, attempt, fence, permissions, active state, lease and deadline. Results must use the assigned deployment and extend the persisted prefix. Cancellation wins over subsequent completion. A lost worker never commits over a replacement.

Prompt/system limits are 32,768/8,192 characters. Output is at most 32,768 characters (at most 128 KiB UTF-8 before JSON escaping); no unlimited token rows or large artifact blobs are added. Streaming batches append contiguously, with safe duplicate detection. Snapshots are not checkpoints; retries restart inference. API restart preserves queued work, attempts, bounded partials and final results in PostgreSQL. See the [SSE contract](../protocols/inference-v1.md).

Usage includes provider-reported input/output token counts when available, worker-measured duration and streaming first-token latency. Non-streaming first-token latency is unknown. Ollama throughput derives from provider counts/generation duration; otherwise rate uses provider output counts and worker timing and is labeled an estimate. Missing counts remain unknown; text chunks/characters are never presented as token counts. Queue wait is derived from durable submission/assignment timestamps. Authenticated workspace-scoped operational metrics include terminal-job failure/cancellation rates and up to 200 recent attempt metadata records, without prompts or response text. Individual results include deployment/provider/node, queue wait, usage and safe classified errors.

API and worker logs omit prompts, responses and keys by default. Explicit result/stream CLI commands intentionally print authorized response data. Synthetic acceptance artifacts contain synthetic text only and remain ignored. Real data, remote access and public exposure still require the separate security gates; no browser sessions or full RBAC are added here.

## Extension points and limitations

- One concurrent inference per worker node; multiple independently provisioned nodes can run concurrently. Existing scheduler concurrency/reservation logic remains authoritative.
- Text chat only; no images, agent runtime, LangGraph, MCP, arbitrary tools or coding execution.
- No automatic fallback, model download, checkpoint continuation, model performance ranking or GPU memory prediction.
- Bounded snapshots use periodic polling, with up to 500 ms API observation delay plus worker batching. They are replaceable provisional text, not a lossless token stream.
- Closing HTTP streams requests cancellation locally; remote-provider computation, billing and repeated-attempt costs need provider-specific guarantees.
- Loopback Ollama and optional HTTPS-compatible providers share the same protocol on Windows/macOS/Linux. Actual CUDA/Metal/AMD performance and physical macOS/Linux inference require hardware tests; no coordinator vendor assumptions exist.
- This local phase provides no production secret store, quotas, rate limits, artifact store, retention purge, remote invitations or internet deployment authorization.

Provider references: [Ollama chat](https://docs.ollama.com/api/chat), [installed models](https://docs.ollama.com/api/tags), [Ollama API and show metadata](https://github.com/ollama/ollama/blob/main/docs/api.md), and [OpenAI chat protocol](https://developers.openai.com/api/reference/resources/chat).
