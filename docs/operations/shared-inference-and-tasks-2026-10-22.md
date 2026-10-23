# Shared inference, Distributed Tasks and corner feedback

This began as an owner-authorized **local source milestone**. It adds the requested screens, APIs, scheduler integration, worker contracts, variable resolution, toasts and Nodes heartbeat indicator. Its original scope excluded engine installation, weights, contributor-host changes, packaging and deployment. The owner subsequently authorized packaging and deployment: coordinator and all three installers are now published as **0.8.0-rc.1**. See the [deployment verification](shared-inference-deployment-2026-10-22.md). Existing worker identity and permissions are preserved. Engine installation and hardware acceptance remain separate.

## What appears in the Command Center

- **Distributed Jobs** (`/distributed`): one model request using **GPUs inside one computer**, **Computers on a fast local network**, or **Computers across locations**. Choose a group actually configured by its owners. Empty setup lists explain what is missing. An unavailable group cannot start. Wide-area submission requires explicit prompt-sharing/performance acknowledgement.
- **Distributed Tasks** (`/distributed-tasks`): the previous Distributed Jobs screen and existing history. Independent tasks run together. Select preceding tasks under Wait for results, or insert an output variable to create the dependency automatically. Final synthesis still waits for all required results.
- **Variables:** copy supported workspace/job/task/agent/model references from the popout into task instructions. Custom variables accept a JSON object, for example `{"project":"Arithmetic"}`, referenced as `{{vars.project}}`; their names appear in the legend. References do not select a different model/agent or grant permissions.
- **Corner feedback:** compact rows styled after the supplied references. Processing remains for the job duration; real completion/error replaces it. Unknown progress is indeterminate. Errors persist until closed. View opens the relevant job. Eight-second success/notification notices are dismissible. Tracking survives refresh/navigation in the same tab; tab storage contains only actor-scoped job IDs/type flags. Sign-out clears it.
- **Nodes:** a small EKG below Heartbeat marks the latest actual receipt in a 30-second window. Offline/stale/unknown data is flat. It does not invent a history of unobserved heartbeats.

Arithmetic example:

```text
Task 1 / task1: Add 1+1.
Task 2 / task2: Add 2+2, then add {{tasks.task1.output}}.
```

Task 2 waits for Task 1's durable output and receives it as quoted data. Readiness requires a worker advertising `task-variables-v1`; old workers continue ordinary tasks and the earlier dependency protocol. This is contextual model execution, not a deterministic arithmetic evaluator. The model remains responsible for its answer.

## Owner-controlled engine setup

A shared engine must already be installed and configured by the participating owners. Every member runs the updated worker source with the same `--shared-inference-config` JSON array. This locally opts that computer into that particular topology. The leader additionally uses `--inference-config` containing the loopback OpenAI-compatible engine provider. Followers need no provider configuration; they continue outbound authenticated heartbeats and advertise group consent. Do not run two Godfather workers under one identity simultaneously.

Create one group per actual engine topology. Replace all example IDs with existing node IDs; do not create replacement node identities. Use a stable new group UUID. Member declarations must match exactly, including order and model alias. Supported engine labels are `llama_cpp` and `vllm`; supported splits are `pipeline` and `tensor`. These are descriptions of an engine configured by its owner, not engine launch commands.

Example group array for two computers:

```json
[
  {
    "id": "10000000-0000-4000-8000-000000000001",
    "name": "Private model group",
    "mode": "local_network",
    "leader_node_id": "20000000-0000-4000-8000-000000000001",
    "node_ids": [
      "20000000-0000-4000-8000-000000000001",
      "20000000-0000-4000-8000-000000000002"
    ],
    "model": "shared-model",
    "engine": "llama_cpp",
    "parallelism": "pipeline",
    "device_count": 2,
    "private_transport": true
  }
]
```

For `single_host`, use only the leader in `node_ids`, with at least two discovered GPUs and the engine configured across those GPUs. For `wide_area`, include the actual consenting computers across locations. Neither location names nor a fixed computer count are coded into scheduling. `private_transport: true` attests owner-configured private engine transport; it does not provision or verify tunnels.

Example leader provider array (keep it owner-local):

```json
[
  {
    "id": "shared-local",
    "provider": "openai_compatible",
    "url": "http://127.0.0.1:18080/v1",
    "shared_inference_group_id": "10000000-0000-4000-8000-000000000001",
    "chat_enabled": true,
    "stream_enabled": true
  }
]
```

The model must appear in the engine's `/v1/models` response. The worker discovers it without downloading weights. Shared providers must remain leader-loopback and cannot use frontier credential connections. Any API-key environment name stays only in the local provider file/environment. All member owners separately opt in and grant normal workspace contribution. Platform administration cannot bypass either requirement.

Source commands, after saving those owner-local files and stopping the previous worker normally:

```text
godfather-worker --url https://YOUR-COMMAND-CENTER --credential-file OWN-WORKER.json --shared-inference-config OWN-GROUPS.json --inference-config OWN-PROVIDERS.json
```

Followers use the same command without `--inference-config`. Existing heartbeat, capability and owner-sharing flags still apply. To use task variables, add `--execute-workflows` alongside the existing inference configuration; no tool permission is added automatically. These commands are instructions for an owner to review; they were not run against contributor hosts.

## Engine configurations and physical acceptance

All three setups route through the same gateway; the selected engine performs the split. For an already installed llama.cpp engine and existing compatible weights, a single-host layer-split configuration can follow this template (paths and supported device flags must match that host):

```text
llama-server --model EXISTING-MODEL.gguf --alias shared-model --host 127.0.0.1 --port 18080 --n-gpu-layers 999 --split-mode layer
```

Tensor mode is an alternative only where the installed build/model/backend supports it. Multi-computer llama.cpp uses its RPC backend; configure the engine with the participating devices over owner-approved private transport. Do not expose RPC on the public internet. Upstream currently describes RPC as fragile/insecure proof-of-concept and warns against sensitive environments. Its direct exposure is unsuitable for deployment by this milestone. vLLM is an alternative on supported hardware with a matching environment across members. See the official [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [RPC](https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md), and [vLLM parallelism](https://docs.vllm.ai/en/stable/serving/parallelism_scaling/) documentation. No Ray, runtime or GPU package is added to Godfather.

Readiness is owner-attested topology plus worker model discovery, actual advertised single-host GPU count, permissions and member health. It does not establish a speedup or prove which devices computed the answer. Before real use, benchmark identical prompts/model settings per setup, verify per-device activity privately on the participating hosts, and test member loss/cancellation with the actual engine. Record latency, tokens/second and engine cleanup. Network transport can make inference slower; wide-area mode is explicitly experimental.

All members are reserved together, including every concurrency slot. A disconnect, credential withdrawal, changed session, model withdrawal or consent loss fences the attempt and fails it safely. Inspect any partial output before submitting a fresh group job. No automatic paid fallback, group replay or recovery of in-flight GPU state occurs. External engine cancellation/unloading remains engine-dependent; a Godfather reservation cannot control unrelated owner processes.

## API compatibility

Canonical tasks: `POST/GET /api/v1/distributed/tasks`, `/options`, `/{id}`, `/{id}/cancel`. Historical `/api/v1/distributed/jobs` remains an alias for task groups and preserves their IDs.

Shared inference: `GET /api/v1/shared-inference/options?workspace_id=...`, `POST /api/v1/shared-inference/jobs`, `GET /api/v1/shared-inference/jobs?workspace_id=...&offset=0&limit=25`. Results, streaming, attempts, cancellation and fenced reports use existing inference/job endpoints. UI history has top/bottom 25-item pagination. No schema migration is required.

## Local validation

Validation results are recorded after execution below. The test database is a separately named disposable PostgreSQL container on loopback; existing local coordinator services and data are untouched. Model responses are controlled fixtures. Browser checks use an isolated fixture API and local Edge, without Google accounts, real keys, live inference, or contributor reconfiguration.

Executed validation:

- Full real-PostgreSQL Python regression: **611 passed, 4 skipped**. The skips require optional pre-existing pinned coding/data sandbox images or Windows symlink permission.
- After the final shared cancellation/session-evidence changes, affected scheduler, inference, task and shared-inference integrations: **79 passed**. Group cancellation remains cancelled after disconnect; engine withdrawal fences completion; completed attempts retain member-session evidence separately from the typed public result.
- Final scheduling/variable run: **51 passed**, including a three-computer one-leader job, locked-leader reservations, and preferred peer-owner first refusal.
- Frontend components: **37 passed**, including timer lifetime, error persistence, variable validation and truthful heartbeat rendering.
- Ruff formatting/lint and repository-wide strict mypy passed. Frontend strict TypeScript, ESLint and production build passed.
- Isolated Edge browser acceptance passed task output variables, dependency edges, corner errors while scrolling, processing beyond eight seconds, success transitions, dark/light and 390px task layout, all three inference mode choices, cross-location consent, restored tracking after refresh, and received/offline Nodes EKG. No browser page errors were recorded. Screenshots were visually inspected.
- Frontend component test transpilation now matches the application's ES2017 target, rather than the compiler's ES5 default, so iterator/Set behavior is actually exercised.

Ignored local evidence: `.cache/shared-inference-regression.log`, `.cache/shared-inference-final-focused.log`, and `.cache/distributed-ui/` (`result.json`, `error-toast.png`, `shared-inference.png`, `heartbeat.png`, plus light/dark/narrow task captures).

These implementation checks establish local source behavior using controlled provider responses. They do not establish physical multi-GPU, mixed-host or cross-location throughput, recipient installer acceptance or paid inference. The subsequent authorized packaging and production checks are recorded in the [deployment verification](shared-inference-deployment-2026-10-22.md). No contributor host was reconfigured.
