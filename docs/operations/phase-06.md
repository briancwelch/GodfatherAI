# Phase 06: Agent runtime, stateful workflows and durable checkpoints

## Scope and prerequisite

Phase 06 was explicitly authorized after confirming Phase 05. Before Phase 06 implementation, the full repository check passed (format/lint/strict typing, 122 Windows tests, frontend format/lint/types/build); all 200 PostgreSQL-backed tests passed without skips, including cancellation, durable results and fencing. A real `qwen3:8b` job passed through the API, native worker and gateway in both streaming/non-streaming modes, and results survived an actual API restart. Phase 05 evidence: `.cache/phase05-runs/567de24eb58348a5943bec7cf20e3758/result.json`. This closure was committed/pushed as `143e14e` before Phase 06 changes.

This phase implements portable immutable agent versions, predefined sequential model/tool workflows, read-only tool grants, central immutable JSON artifacts, transactional checkpoints, fenced same-node process-restart recovery and authenticated workflow APIs. Read [architecture](../architecture/agent-runtime.md), [ADR 0006](../decisions/0006-sequential-workflows-and-artifacts.md), and [API/protocol](../protocols/agents-v1.md).

The user also requested hybrid local/frontier BYOK planning only. [That plan](../architecture/byok-plan.md) is saved; it is **not implemented or authorized for implementation**. Phase 06 workflow configuration accepts loopback providers only, validated before provider discovery. No cloud calls, paid fallback, keys/secret stores, cost ledger, grant/approval system or new frontier adapter is introduced.

## Local startup and storage

Use the [Windows/macOS/Linux setup](setup.md) and existing ignored `.env`. From the repository root:

```text
uv sync --locked --all-packages
docker compose --profile tools build api api-test migrate
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Apply the additive migration explicitly; the head is now `0004_agent_runtime`. Existing identities, jobs, inference results and legacy agent/checkpoint rows remain. Old schema-only agents are disabled and unsupported rather than treated as executable definitions. Startup/readiness never silently apply migrations. Downgrades/reset tests are restricted to the guarded disposable `godfather_test` database.

API: **http://localhost:8000/api/v1**, readiness: **http://localhost:8000/health/ready**, unchanged disconnected shell: **http://localhost:3000**. Public domains remain proposed and unused.

Compose mounts the new local `artifacts-data` named volume only on the API, at `/var/lib/godfather/artifacts`; the non-root API otherwise keeps its read-only filesystem. Database rows own artifact visibility and metadata; clients never receive host paths. Native API development uses ignored `.cache/artifacts` or an explicitly configured `GODFATHER_ARTIFACT_DIRECTORY`. Use an owner-private Windows directory/ACL, or POSIX 0700 directory/0600 files. Never put the artifact store in a public web directory.

Database and artifacts must be retained/backed up together. An API restart/recreation retains the named volume; `docker compose down` without volume deletion retains both database and artifact volumes. Do not delete volumes or orphan files automatically. Transaction failures may leave unreferenced files; production retention/GC and a complete backup/restore runbook remain later work. Missing/corrupt referenced files block restoration visibly with a 503.

## Define and run a local workflow

Reuse [Phase 03 private credential provisioning](phase-03.md) and [Phase 04 private workspace provisioning](phase-04.md). Each worker has its own node credential and owner. No identities or keys are preseeded. Use only synthetic instructions during this local development phase.

If Ollama is already installed/running, use its existing discovered model identifier. No command below installs it, changes its binding or pulls a model. Create the worker-owned provider configuration as described in [Phase 05](phase-05.md), using loopback Ollama or an already approved local compatible provider.

Create a portable data-only demonstration definition and store it in your private ignored directory. Replace the model placeholder with the exact installed identifier:

```text
uv run --locked --all-packages python -m scripts.workflows demo-definition --model YOUR_INSTALLED_MODEL --definition-file .cache/credentials/demo-agent.json
uv run --locked --all-packages python -m scripts.workflows create --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID --definition-file .cache/credentials/demo-agent.json
uv run --locked --all-packages python -m scripts.workflows list --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID
```

The definition file is exclusively created; existing files are not overwritten. The backend creates a stable agent ID and immutable version-1 row. The demo has three steps: structured model plan, authorized deterministic `plan.describe@1`, and model summary. It is configuration, not a special hardcoded agent type. Edit your private copy or create other names/configurations as needed; append versions rather than mutating one already submitted.

Start the worker, granting both the tool reference and required permission:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/worker.json --inference-config .cache/credentials/providers.json --execute-workflows --allow-tool plan.describe@1 --allow-tool-permission plan.read
```

This uses physical discovery by default and no host services. It does not grant filesystem, shell, Git, SQL or account access. Platform administrators cannot supply the node owner's grants. Cross-owner execution still additionally requires that node owner's workspace access, existing owner/workspace allowlists and a compatible contribution policy. Missing grants leave jobs queued or refuse subsequent tool transitions. One slot is advertised/executed per worker; multiple nodes remain dynamically managed.

Create a private plain UTF-8 `.cache/credentials/instruction.txt` containing a synthetic instruction, then submit using the actual returned agent ID:

```text
uv run --locked --all-packages python -m scripts.workflows submit --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID --agent-id AGENT_UUID --agent-version 1 --instruction-file .cache/credentials/instruction.txt
uv run --locked --all-packages python -m scripts.workflows inspect --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows steps --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows checkpoints --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows result --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows cancel --credential-file .cache/credentials/admin.json --job-id JOB_UUID
```

Submit/create commands print identifiers/status, not sensitive instructions. Explicit inspect/result/artifact commands intentionally display authorized private data. Prompt contents, tool outputs and credentials are omitted from application/worker logs and audit events. Create a new version with `version --agent-id ... --agent-version CURRENT_VERSION --definition-file ...`; enable/disable one version with those actions. Disabling blocks new starts/steps but lets an already started valid step checkpoint; use cancellation to stop execution.

## Repeatable validation and process interruption

Run tests and live acceptance serially. Do not reset `godfather_test` while running live smoke tests, even though the application database is separately named.

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
uv pip check
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_agent_runtime
```

The default acceptance starts its own ephemeral loopback model fixture and actual native worker processes. It provisions synthetic credentials/workspace/agent and completes all three steps normally. It then runs with a simulator-only barrier after checkpoint 1, stops that actual process, waits for coordinator-owned health/lease expiry, verifies retry, restarts the actual API and retains its artifact volume, and starts a new worker process with the same node credential. The new attempt restores checkpoint 1, skips the committed plan step and completes the two remaining steps. It verifies three unique completed step records, checkpoint versions 1/2/3, two attempts/higher fence, interruption/resume/completion history, stale old-session rejection and unchanged final results.

For the real already-installed local model:

```text
uv run --locked --all-packages python -m scripts.check_agent_runtime --ollama --model YOUR_EXACT_INSTALLED_MODEL
```

This performs the same normal and interrupted/recovered workflows through Ollama. It performs no model download, paid provider request, account access or system configuration change. The acceptance's node hardware advertisement remains explicitly simulated; a real model invocation establishes the local inference path, not simulated GPU performance. Use the normal worker command for physical capability discovery.

Evidence and synthetic output remain in ignored `.cache/phase06-runs/RUN_UUID/`. Every exit stops its own processes/server and attempts to cancel its own jobs and revoke its two credentials. Completed rows/artifacts remain for inspection. The `--pause-after-checkpoint N` worker flag is a documented, simulator-only fault-injection barrier, not a production workflow pause/approval feature. A new session must wait for the old one to become offline; no process inherits another live session or lease.

The CI OS matrix executes portable tests on Windows/macOS/Linux and Python 3.12/3.14 when run. The serial Linux container job now includes the native mock workflow/recovery acceptance. Configuring CI is not proof of executed remote results.

## Validation and evidence

The native mock demonstration passed in `.cache/phase06-runs/09c0c49e9ff9488484d02ae3f3307f0a/result.json`. Real Ollama `qwen3:8b` then passed both normal and interrupted/recovered demonstrations in `.cache/phase06-runs/075e70cacb1f4be7810f92f6d55a1beb/result.json`. Both had three committed steps, versions 1/2/3, no repeated committed plan step, actual process interruption/API restart, successful same-node recovery and rejected stale writes. The real plan belonged to the original attempt; the tool and summary belonged to the new attempt. No installation or download occurred. After the final compact-reference and definition-size changes, the native mock acceptance was repeated successfully against the rebuilt API: `.cache/phase06-runs/e394725e1774429dbc17cc6b541efa2c/result.json`. Cleanup succeeded, including stopping owned worker processes and revoking both synthetic credentials.

Final checks actually executed locally:

| Check                                       | Result                                                                                                                                                                                         |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python scripts/dev.py check`               | Passed: Ruff format (91 files), Ruff lint, strict mypy (65 source files), Windows pytest (141 passed, 92 database cases intentionally skipped), Prettier, ESLint, TypeScript and Next.js build |
| Rebuilt `api`, `api-test`, `migrate` images | Passed                                                                                                                                                                                         |
| Full PostgreSQL container pytest            | **233 passed, zero skipped** in 39.37 seconds; includes all 92 database cases, migration upgrade/downgrade/schema checks and 14 workflow integration cases                                     |
| `docker compose config --quiet`             | Passed                                                                                                                                                                                         |
| `uv pip check`                              | Passed: 45 installed packages compatible                                                                                                                                                       |
| `git diff --check`                          | Passed                                                                                                                                                                                         |

The workflow tests include artifact rollback/corruption, node grants, immutable versions, workspace isolation, malformed model output, cancellation during blocked inference, step deadlines, concurrent duplicate checkpoints, restart restoration, stale fencing and lease expiry during storage I/O. Unit tests also cover bounded definitions, compact/historical model references and refusing remote workflow configuration before discovery. Native acceptance evidence is additional to these deterministic tests. Physical OS/backend validation remains limited as described below.

## Limitations and security boundary

- Sequential bounded JSON workflows only; no autonomous tools, parallel branches, multi-agent supervisors, visual engine, coding/WordPress/image agents or full dashboard.
- Only one node process executes a workflow attempt. Process recovery is same-node and requires an authenticated replacement session after lease/deadline expiry; compatible cross-node automatic failover remains Phase 07.
- Model output must satisfy the declared schema. Unsupported JSON-mode providers or malformed plans fail explicitly; there is no silent fallback or unvalidated tool execution.
- Only known, read-only, deterministic tools are allowed. Non-idempotent/external operations are rejected, so no uncertain external operation is automatically retried. Future support needs explicit approval/reconciliation design.
- Artifacts are immutable bounded JSON, not an unrestricted file ingestion API or cloud object store. Complete production retention, quota and backup/restore verification remain later phases.
- Physical macOS/Linux inference, CUDA/Metal/AMD execution, public/remote deployment and remote CI are not established by Windows native processes, Linux containers or OS mocks.
- The user-added BYOK requirement is preserved in `AGENTS.md` with its explicit planning-only boundary. No billing controls, native frontier providers, credential sharing or cloud failover have been implemented.

## Files changed

| Area              | Files                                                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Runtime           | `packages/agent-runtime/pyproject.toml`, `src/godfather_agent_runtime/{__init__,tools}.py`                                                                                              |
| Contracts         | `packages/shared-schemas/src/godfather_contracts/{__init__,execution,agents,jobs}.py`                                                                                                   |
| API/persistence   | `apps/api/pyproject.toml`, `src/godfather_api/{agents,artifacts,workflow_service,app,config,models,jobs,nodes,scheduler}.py`                                                            |
| Schema/storage    | `infrastructure/migrations/versions/0004_agent_runtime.py`, `infrastructure/docker/api.Dockerfile`, `compose.yaml`                                                                      |
| Worker/gateway    | `packages/worker/pyproject.toml`, `src/godfather_worker/{agents,cli,inference}.py`, `packages/model-gateway/src/godfather_model_gateway/{__init__,providers}.py`                        |
| Tools/tests       | `scripts/{workflow_demo,workflows,check_agent_runtime}.py`, `tests/{workflow_helpers,test_agent_runtime,test_model_gateway}.py`, `tests/integration/{test_workflows,test_inference}.py` |
| Workspace/CI/docs | `pyproject.toml`, `uv.lock`, `.github/workflows/checks.yml`, `AGENTS.md`, `README.md`, setup/security/compatibility/protocol docs, new architecture/ADR/runbook                         |

Stop after Phase 06. Phase 07 and BYOK implementation both require separate explicit authorization.
