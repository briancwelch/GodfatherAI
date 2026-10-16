# Cross-platform compatibility policy

The coordinator is a modular monolith, intended for an independent Ubuntu Linux VPS. Development must also run locally on Windows with Docker Desktop/WSL2, macOS, and Linux. No contributor desktop is a production coordinator requirement.

## Development baseline

Python 3.14 and Node.js 24.22.0 are the selected development runtimes. Python source targets 3.12+ syntax; CI includes Python 3.12 on Linux and 3.14 on Windows, macOS, and Linux. Frontend checks cover all three operating systems. CI configuration is not evidence of completed CI runs.

Use standard-library Python for portable development helpers, argument arrays rather than shell strings, paths derived from the repository, UTF-8, and LF line endings. Windows paths containing spaces are supported. Do not require PowerShell 7, GNU Make, Bash, or a global JavaScript package manager beyond npm.

Container images must support Linux amd64 and arm64; do not pin the Compose platform to one contributor's CPU. Verify actual image manifests and native builds when updating image tags. Container checks on Linux amd64 do not establish arm64 execution evidence.

## Future workers (design constraint, no Phase 01 implementation)

- Portable Python core; adapters isolate process spawning, shell/path handling, discovery, sandboxing, and service management.
- Windows 11, supported macOS on Apple Silicon and Intel where feasible, and mainstream Linux including Ubuntu.
- Detect OS/version, architecture, CPU/RAM, accelerators/backends, runtimes, models, toolchains, limits, and supported isolation modes. No mandatory GPU, CUDA, or vendor parity.
- Native worker installation and service setup require node-owner approval. Docker is not an assumption about worker GPU support.
- Jobs may migrate only when OS, architecture, dependencies, runtime, model, tools, permissions, and artifact requirements match.
- Checkpoints and artifacts must be centrally accessible, durable, portable and versioned. Local paths, unsaved files and GPU state are not recoverable checkpoints.

Multiple simulated worker processes must be able to share one physical development machine in later phases. Simulated Windows/macOS labels test matching logic; physical OS runners test adapters. GPU/inference backends require actual hardware validation and must be marked untested until exercised.

No worker, protocol, scheduler, model gateway, checkpoint store, or failover implementation is included in Phase 01.
