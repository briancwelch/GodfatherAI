# Owner-approved llama.cpp setup in Consigliere

Status: owner authorized local implementation, 2026-10-23. Roll into the local
model scan and permission changes in ADR 0030. No release, packaging, push or
deployment is authorized by this milestone.

The owner separately authorized builds and deployment on 2026-10-24. See the
[release report](../operations/shared-inference-release-2026-10-24.md).
Coordinator and all three native installers are published as **0.10.0-rc.3**.

The worker now configures shared inference through its own **Shared Inference**
tab. The user chooses an installed GGUF model, workspace and participating
computers. Each computer's owner selects devices detected by its local runtime
and approves on that computer. The initiator can then **Configure and Start**.
This extends the existing shared-inference scheduler and provider-neutral model
gateway; it does not introduce another orchestration service.

## Execution and consent

PostgreSQL stores immutable proposals, per-computer approvals bound to worker
credentials, public TLS certificates, private network addresses, run generations
and lifecycle reports. Worker-only authenticated endpoints can approve only the
calling computer. Human administrator sessions cannot approve contributor hosts.
Normal workspace and node-owner contribution permissions still apply. Revocation
and withdrawal invalidate scheduling immediately, including in-flight result
acceptance through existing fencing. Each node may belong to one enabled engine.

The worker separately stores its exact approved proposal, credential identity,
devices and model path locally. A coordinator start request alone cannot grant
execution. Changed credentials, devices, endpoints or proposals require local
approval again. Private keys and model paths do not enter coordinator state.
Paused workers do not start groups automatically. Explicit local approval allows
the initiating computer to start that exact group until participation is withdrawn.

The worker finishes current ordinary work before starting the engine. Idle
sessions are retired under a node lock; a live attempt cannot be reset. Managed
sessions advertise only the group and selected resources and cannot accept
ordinary jobs. Stopping restores normal saved contribution settings. Existing
leases, reservations, checkpoint behavior and stale-result rejection remain.
This is process-level lifecycle management, not a promise of hard OS memory caps.

## Runtime and transport

Use upstream llama.cpp **b11846**, pinned by archive SHA-256 for each supported
platform/backend in the bundled catalog. Reuse verified files, or require the
owner's explicit download checkbox before installing a portable copy under the
worker data folder. Check installed hashes before reuse. No services, models,
drivers, accounts or firewall rules are installed automatically. Cryptography is
already a coordinator dependency; the worker now declares it directly for local
certificate generation and TLS identities.

Windows and Linux offer CPU or Vulkan builds; Apple Silicon offers CPU/Metal;
Intel macOS offers CPU. Available devices come from the selected actual build's
inventory. Vulkan can use supported installed GPU drivers without requiring
CUDA. These options describe supported code paths, not hardware acceptance on
every OS. Only the initiating computer loads the selected model file; additional
computers run selected RPC devices.

Upstream labels raw RPC experimental and insecure. Keep it bound to loopback.
Network participants communicate through a bounded mutual TLS bridge using
per-group identities and exact certificate pins. Only explicitly approved
private addresses are accepted; an existing LAN/Tailscale route is required.
No public inbound ports, automatic tunnels or router configuration are added.
The leader's OpenAI-compatible model endpoint also remains loopback-only.
Disable agent/web features and remote model fetching, and strip inherited engine
options and provider secrets from process environments. Only owned child
processes and bridge connections are stopped.

## Limits and compatibility

The scan still shows at most 128 installed models and provider advertisements
retain their existing limits. Compatible Ollama model layers can be selected by
their scanned model names; their blob paths remain local. Other model formats
require their existing adapters. GGUF presence is a candidate; successful model
loading and health discovery establish runtime readiness.

One active group is advertised per desktop worker. The setup UI lists up to eight
recent groups, keeping enabled groups first. Each node allows eight pending or
enabled invitations. Proposals allow 64 computers and 32 selected devices per
computer, within the existing 1024-device shared-group contract. This does not
assert those limits are practical performance targets.

Legacy manually configured shared groups remain supported. New runtimes advertise
`shared-engine-setup-v1`; older workers are excluded from wizard invitations.
Migration 0017 adds setup/consent tables without replacing identities or job history.
Deployment must update the coordinator schema and workers together when separately
authorized.

Primary upstream references: [llama.cpp](https://github.com/ggml-org/llama.cpp),
[pinned release](https://github.com/ggml-org/llama.cpp/releases/tag/b11846),
[RPC source](https://github.com/ggml-org/llama.cpp/blob/b11846/tools/rpc/rpc-server.cpp),
[server options](https://github.com/ggml-org/llama.cpp/blob/b11846/tools/server/README.md).
