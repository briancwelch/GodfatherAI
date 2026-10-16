# Phase 05: Local inference and provider gateway

## Scope and prerequisite

Phase 05 was explicitly authorized. Before edits, Phase 04 passed Python formatting/lint/strict typing, 84 Windows unit tests, all 143 PostgreSQL-backed tests without skips, frontend formatting/lint/type/build, and the native scheduler acceptance. That acceptance completed 100 jobs across two workers with 110 nonoverlapping attempts, preserved queued jobs through actual API/PostgreSQL restarts, left an incompatible job queued, and recovered a stopped worker's job on a surviving worker with a new fence. Evidence: `.cache/phase04-runs/bd98ed06f5d44e89a4ccfd4826bbfa92/result.json`.

This phase adds the provider-neutral gateway, Ollama/OpenAI-compatible adapters, model advertisements and matching, opt-in text execution, authenticated result/model/metrics APIs, and attempt-aware SSE. Read [architecture](../architecture/model-gateway.md), [ADR 0005](../decisions/0005-worker-local-model-gateway.md), and [typed inference protocol](../protocols/inference-v1.md).

No agent orchestration, model download, image workflow, MCP, coding agent, full dashboard, remote integration or cloud deployment is included. The dashboard remains the existing disconnected shell. Phase 06 requires separate explicit authorization.

## Start local services

Use the [existing cross-platform setup](setup.md), ignored `.env`, and Docker Desktop/WSL2 on Windows. All commands run from the repository root:

```text
uv sync --locked --all-packages
docker compose --profile tools build api api-test migrate
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

There is no new database revision: typed deployment/partial/result metadata uses existing JSONB columns. The schema head stays `0003_durable_scheduler`. The migration command remains an explicit readiness check; startup never changes schema.

API: **http://localhost:8000/api/v1**, readiness: **http://localhost:8000/health/ready**, disconnected shell: **http://localhost:3000**. Publishing remains loopback-only, databases internal. Nothing uses the proposed public domains or DigitalOcean.

## Existing Ollama installation

Do not install Ollama, start an installed service, change its binding/firewall, or download a model without owner authorization. If it is already running, inspect `http://127.0.0.1:11434/api/tags` or run `ollama list`. Choose the exact returned identifier, including tag. The worker never calls model pull/create/delete endpoints.

Create `.cache/credentials/providers.json` in your owner-private credential directory. This file contains worker-local configuration, never coordinator settings:

```json
[
  {
    "id": "local-inference",
    "provider": "ollama",
    "url": "http://127.0.0.1:11434",
    "timeout_seconds": 120
  }
]
```

Provision an administrator, private workspace, and individually authenticated worker using the existing [Phase 03](phase-03.md) and [Phase 04](phase-04.md) instructions. Use actual IDs, with no production credentials. Start the worker on the machine hosting Ollama:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/worker.json --inference-config .cache/credentials/providers.json
```

Physical discovery is portable and requires no CUDA. macOS providers may use Metal internally; the coordinator makes no OS-specific inference calls. No OS service is installed. Keep the terminal running. Inference advertises one concurrency slot; `--concurrency` other than 1 is refused in this phase. Existing contribution policies and repeated `--allow-owner UUID`/`--allow-workspace UUID` options still control cross-owner execution. Platform administration cannot supply that consent.

List available deployments with the administrator credential and actual workspace UUID:

```text
uv run --locked --all-packages python -m scripts.inference models --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID
```

Create a private `.cache/credentials/inference-request.json` using the [request example](../protocols/inference-v1.md), replacing the workspace and model identifiers. Keep prompts out of shell arguments/history. Submit and inspect using the returned job UUID:

```text
uv run --locked --all-packages python -m scripts.inference submit --credential-file .cache/credentials/admin.json --request-file .cache/credentials/inference-request.json
uv run --locked --all-packages python -m scripts.inference stream --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.inference result --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.inference metrics --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID
uv run --locked --all-packages python -m scripts.inference cancel --credential-file .cache/credentials/admin.json --job-id JOB_UUID
```

Result/stream commands intentionally display authorized response text. Streams close after at most 30 seconds; rerun/reconnect for the current snapshot. Clients replace text on each snapshot and clear it on reset/invalidation. If no compatible model exists the job remains `PENDING`; no alternate model is selected. Set both streaming flags false for a non-streaming job. Changing available models requires no application source change or coordinator restart; workers refresh discovery between attempts.

## OpenAI-compatible providers

A compatible endpoint can be local or an explicitly authorized remote service. Merely supporting remote configuration does not authorize contacting an account, incurring costs or sending private data. Configure only approved endpoints; none is preconfigured or contacted by tests.

```json
[
  {
    "id": "approved-provider",
    "provider": "openai_compatible",
    "url": "https://YOUR_APPROVED_HOST/v1",
    "api_key_env": "GODFATHER_APPROVED_PROVIDER_KEY",
    "chat_enabled": true,
    "stream_enabled": true,
    "declared_capabilities": ["completion"],
    "timeout_seconds": 120
  }
]
```

Set the named environment variable securely in the worker's environment; never put its value in job/config payloads, committed files or logs. For an already-approved local compatible provider, HTTP is permitted only on loopback. Certificate validation is mandatory remotely; redirects and environment proxies are disabled. Discovery does not certify capabilities, context sizes or operation support. Capability-based selection must explicitly accept declarations; exact model identifiers still require enabled operations.

## Repeatable tests and native demonstration

The integration reset guard is unchanged: only `environment=test`, `godfather_test`, and `GODFATHER_RUN_INTEGRATION=1` permit migration-reset tests. Never run reset tests concurrently with live acceptance.

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
uv pip check
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_model_inference
```

The default native acceptance starts its own loopback mock Ollama server and native worker, provisions fresh synthetic identities/workspace, advertises a model, submits streaming and non-streaming jobs, reads attempt-tagged SSE, verifies final results and metadata, checks worker logs for prompt/credential leaks, then stops its own processes/server and revokes its credentials. Jobs/evidence remain for inspection. It never replaces a real provider or binds port 11434. Evidence is under ignored `.cache/phase05-runs/RUN_UUID/`. Mock results are labeled `mock_ollama`; their token figures are fixtures, not hardware measurements.

With an **already running** Ollama and an **already installed** suitable model, use:

```text
uv run --locked --all-packages python -m scripts.check_model_inference --ollama --model YOUR_EXACT_INSTALLED_MODEL
```

This runs the same full API/scheduler/native-worker/client path against loopback Ollama and labels evidence `real_ollama`. It does not download anything. The simulated advertisement used by the smoke is clearly labeled; a real provider invocation establishes inference on this host, not simulated CPU/GPU performance. Use the normal worker command for actual host discovery.

The CI OS matrix covers portable Python/provider/matching tests on Windows/macOS/Linux and Python 3.12/3.14. Its Linux container job now also includes native-worker/mock-provider acceptance. Configuration does not establish an executed remote CI run.

## Validation and unresolved gate

Executed on 2026-10-15 with Windows x64/Python 3.14.8 and Docker Desktop/WSL2 Linux amd64:

| Check                                 | Actual result                                                                                                                                                                                                                                                                           |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 04 prerequisite                 | Full repository checks, 143 PostgreSQL tests, and native 100-job/restart/worker-loss acceptance passed before edits                                                                                                                                                                     |
| Python formatting/lint                | Passed; 71 Python files formatted consistently                                                                                                                                                                                                                                          |
| Strict typing                         | Passed; 50 source files checked                                                                                                                                                                                                                                                         |
| Windows database-free tests           | **122 passed**; 78 PostgreSQL cases deliberately skipped here and executed separately below                                                                                                                                                                                             |
| Complete built-image PostgreSQL suite | **200 passed**, no skips, including 78 integration cases and the preserved 100-job scheduler workload                                                                                                                                                                                   |
| Provider/model coverage               | Streaming/non-streaming Ollama/OpenAI-compatible mocks, discovery/provenance, exact model matching, unknown resources, OS mocks, transport/protocol failures, total timeouts and HTTP cancellation                                                                                      |
| Persistence/security coverage         | Registration updates, same model on multiple nodes, workspace/owner restrictions, queueing, bounded contiguous output, live SSE partial/final snapshots, reconnection, API/pool recreation, lease/deadline expiry, stale reports after replacement, cancellation races and retry policy |
| Old synthetic protocol                | New optional fields omitted from synthetic assignments; explicit compatibility regression passed                                                                                                                                                                                        |
| Frontend                              | Prettier, ESLint, strict TypeScript and production build passed; dashboard source unchanged                                                                                                                                                                                             |
| Containers/dependencies               | Final API/test/migration images built; migration readiness, Compose validation, `uv pip check` and Git whitespace checks passed                                                                                                                                                         |
| Native worker demonstration           | Actual outbound worker process discovered the loopback mock model and completed streaming and non-streaming jobs through the local API/scheduler/gateway/SSE/result path                                                                                                                |
| Privacy/cleanup                       | Acceptance verified no prompt/run credentials in its worker log; owned worker/server stopped and two run credentials revoked; synthetic records/evidence retained                                                                                                                       |
| Real Ollama                           | **Not executed: loopback API unavailable**, both before implementation and on final recheck                                                                                                                                                                                             |

Final native evidence: `.cache/phase05-runs/ceb56288d92448e1aeb414eb135d0c8f/result.json`, with its SSE captures and worker log beside it. An earlier complete acceptance also passed in `394566e6c6bf4078a238be4f4963d033`. Both are explicitly labeled `mock_ollama`; their token counts/rates are deterministic fixtures, not actual model throughput. Local API/shell remain healthy and loopback-only.

Initial implementation checks exposed test-module namespace typing ambiguity, fixed by explicit test package markers. Review also caught older strict worker compatibility and cancellation during an output upload; both now have passing regressions. No unresolved local formatting/lint/type/test failure remains. Remote CI is configured but has not been claimed as executed.

Real Ollama was not reachable at `127.0.0.1:11434`, and its executable was not found on the execution shell's PATH. This does not prove it is absent from every local installation directory. No installation, model download or system change was attempted. The roadmap's real-local-model gate cannot be claimed from mocks; it remains open until an already installed model can be exercised with the command above. Implementation is saved on `phase-05-model-gateway`; this does not declare the real-inference gate passed.

Physical macOS/Linux inference and CUDA/Metal/AMD acceleration remain unverified. Local Windows native execution, Linux container tests and mocked platform compatibility are separate evidence. Compatible-provider behavior beyond the standard chat/SSE contract, production security/retention controls, large artifact storage and actual remote failover remain later work.

## Files changed

| Area          | Files                                                                                                                                                                                                                                   |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gateway       | `packages/model-gateway/pyproject.toml`, `src/godfather_model_gateway/{__init__,providers}.py`                                                                                                                                          |
| Contracts     | `packages/shared-schemas/src/godfather_contracts/{__init__,jobs,inference}.py`                                                                                                                                                          |
| API/scheduler | `apps/api/src/godfather_api/{app,jobs,nodes,scheduler,inference}.py`                                                                                                                                                                    |
| Worker        | `packages/worker/pyproject.toml`, `src/godfather_worker/{cli,client,jobs,inference}.py`                                                                                                                                                 |
| Tools         | `scripts/{inference,check_model_inference}.py`                                                                                                                                                                                          |
| Tests         | `tests/{__init__,test_model_gateway,test_inference_matching}.py`, `tests/integration/{__init__,test_inference}.py`                                                                                                                      |
| Workspace/CI  | `pyproject.toml`, `uv.lock`, `.github/workflows/checks.yml`                                                                                                                                                                             |
| Docs          | `README.md`, `docs/architecture/{model-gateway,compatibility,security-foundation}.md`, `docs/decisions/0005-worker-local-model-gateway.md`, `docs/protocols/{inference-v1,worker-v1,jobs-v1}.md`, `docs/operations/{phase-05,setup}.md` |

Stop after Phase 05. Do not begin Phase 06 without explicit approval, and do not treat the unverified real-inference gate as passed.
