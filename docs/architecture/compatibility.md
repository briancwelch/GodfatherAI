# Cross-platform compatibility policy

## Current Phase 07–08 recovery

The original same-node restriction below is superseded by compatible cross-node
recovery. OS, architecture, runtime/dependency/toolchain, model, hardware/resource,
workflow version and independent owner/workspace checks remain mandatory. Committed
JSON artifacts are served by the existing coordinator store; worker-local files or
GPU memory are never assumed portable. Tests cover simulated Windows-to-macOS/Linux
recovery and incompatible backups. Physical OS/GPU evidence remains separate. See
[Phase 07–08](../history/phases.md#phase-07-08).

## Phase 06 workflows and checkpoint artifacts

The agent runtime and deterministic read-only tool registry use portable Python and JSON references. The coordinator owns immutable output/checkpoint files in its persistent local volume; workers restore through authenticated, fenced APIs and never serialize host paths, GPU state, open handles or Python process objects. File operations are isolated in the local storage backend. Worker/model operations remain OS/provider-neutral; JSON-mode hints do not change older inference assignment shapes. Tool and owner-permission checks apply on both the backend and worker.

Workflow jobs may recover on their originally selected node after an authenticated process restart. Agent definitions are never tied to that node. Cross-node automatic failover remains Phase 07. The native acceptance runs normal and interrupted workflows on one host with explicitly simulated resource labels, with mock and real Ollama evidence reported separately. Physical Mac/Linux and CUDA/Metal/AMD inference are unverified unless separately exercised. See [Phase 06](../history/phases.md#phase-06). Earlier sections record historical phase scope.

## Phase 05 text inference

The provider-neutral gateway uses portable asynchronous HTTP on Windows/macOS/Linux. An explicitly opted-in worker executes one inference at a time against owner-configured loopback Ollama or an approved OpenAI-compatible endpoint. Providers manage CPU/CUDA/Metal/AMD execution internally. The coordinator matches advertised OS/architecture/resources/backend requirements without vendor-specific inference code. Provider-reported capabilities, configured declarations, simulated telemetry and physically executed inference are distinct evidence.

No model, GPU vendor, node, user or geographic location is hardcoded into model selection. Model availability is dynamically registered. Older registration-only workers remain valid; older synthetic assignments omit the new optional inference fields. No physical Mac/Linux or GPU inference result is established by mocked tests. See [gateway architecture](model-gateway.md) and [Phase 05 evidence](../history/phases.md#phase-05). Earlier phase sections below record their historical scope.

The coordinator is a modular monolith, intended for an independent Ubuntu Linux VPS. Development must also run locally on Windows with Docker Desktop/WSL2, macOS, and Linux. No contributor desktop is a production coordinator requirement.

## Development baseline

Python 3.14 and Node.js 24.22.0 are the selected development runtimes. Python source targets 3.12+ syntax; CI includes Python 3.12 on Linux and 3.14 on Windows, macOS, and Linux. Frontend checks cover all three operating systems. CI configuration is not evidence of completed CI runs.

Use standard-library Python for portable development helpers, argument arrays rather than shell strings, paths derived from the repository, UTF-8, and LF line endings. Windows paths containing spaces are supported. Do not require PowerShell 7, GNU Make, Bash, or a global JavaScript package manager beyond npm.

Container images must support Linux amd64 and arm64; do not pin the Compose platform to one contributor's CPU. Verify actual image manifests and native builds when updating image tags. Container checks on Linux amd64 do not establish arm64 execution evidence.

## Worker compatibility

- Portable Python core; adapters isolate process spawning, shell/path handling, discovery, sandboxing, and service management.
- Windows 11, supported macOS on Apple Silicon and Intel where feasible, and mainstream Linux including Ubuntu.
- Detect OS/version, architecture, CPU/RAM, accelerators/backends, runtimes, models, toolchains, limits, and supported isolation modes. No mandatory GPU, CUDA, or vendor parity.
- Native worker installation and service setup require node-owner approval. Docker is not an assumption about worker GPU support.
- Jobs may migrate only when OS, architecture, dependencies, runtime, model, tools, permissions, and artifact requirements match.
- Checkpoints and artifacts must be centrally accessible, durable, portable and versioned. Local paths, unsaved files and GPU state are not recoverable checkpoints.

Phase 03 implements a portable installable Python registration/health worker and mocked OS discovery adapters. Four explicitly labeled Windows/macOS simulation profiles can run as separate processes on one development machine. Simulated labels and discovery mocks do not establish physical OS/GPU behavior. The existing CI OS matrix covers worker tests when executed. GPU/inference backends require actual hardware validation and must be marked untested until exercised.

Phase 01 included no worker implementation; Phase 03 adds protocol v1 registration and health only. Scheduling, model execution, checkpoint storage and failover remain later phases. Unknown architectures and unavailable telemetry are reported explicitly; backend discovery is not inference certification. See [Phase 03](../history/phases.md#phase-03).

## Phase 04 synthetic execution

The portable worker can opt into bounded synthetic jobs with a separate additive execution contract. Matching checks actual advertised OS/architecture, capabilities, exact runtime/dependency/toolchain/model labels, sandbox mode and known resources. Version requirements belong in exact labels. Resource reservations and concurrency limits are enforced transactionally. Existing registration-only workers receive no jobs. Windows/macOS profiles on a Windows host remain simulations. No shell, actual coding, models, GPU inference, checkpoint restoration or external side effects are executed. See [Phase 04](../history/phases.md#phase-04).
