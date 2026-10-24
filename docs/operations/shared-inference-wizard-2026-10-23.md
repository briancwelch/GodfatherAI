# Set up Shared Inference in Consigliere

Published in **0.10.0-rc.3**, 2026-10-24, together with local model scanning,
node permissions, the reconnect warning and update feedback. Update Consigliere
through **File > Check for updates**. See the
[release verification](shared-inference-release-2026-10-24.md). The source
milestone's earlier validation record below remains historical.

## User flow

1. Connect each computer using the updated worker source and grant its normal
   workspace contribution permission. Open **Shared Inference → Set up Shared
   Inference** on the computer that holds the model.
2. Choose an installed compatible GGUF model. **Scan for Local Models** populates
   the list; **Browse installed model** selects another existing file. Compatible
   Ollama model layers found by the scan are also offered by model name. Nothing
   downloads model weights. Choose the workspace and a group name.
3. Choose **GPUs in this computer**, **Computers on a local network**
   for a fast LAN, or **Computers across locations**.
   Include this computer. Continue to owner approvals.
4. On each participant's **Shared Inference** tab, select the group, choose its
   engine backend, and click **Detect available GPUs**. To obtain the portable
   pinned engine for that backend, explicitly enable **Allow verified llama.cpp
   runtime download** first. Select the GPU(s) and/or CPU that this owner wants
   to contribute. A single-computer group requires two or more GPUs.
5. For network peers, choose that computer's existing private LAN or Tailscale
   address and an available port. Each owner clicks **Approve this computer**
   and reviews the participation notice. The initiating computer uses its
   selected local model file; other computers do not need their own weights.
6. The initiating computer clicks **Configure and Start** once every owner has
   approved. Participants finish their current ordinary jobs, start their
   selected devices, and report progress. The initiator loads the model after
   peers are ready. Wait for **Shared engine ready**.
7. Open Command Center **Distributed Jobs** and choose this shared group. Normal
   workspace model restrictions still apply. If the workspace restricts models,
   its owner/admin must permit the group's `shared-<group UUID without hyphens>`
   alias. Wide-area jobs retain their explicit prompt-sharing acknowledgement.

Each computer reserves its selected devices for the engine while enabled.
**Stop and withdraw this computer** ends local participation and stops the group.
**Pause** or quitting stops the local engine; the group stops when the coordinator
receives that report. A coordinator connection loss stops local engines after
approximately 30 seconds without a successful setup refresh. Worker updates wait
for a shared engine to be stopped before installation. Ordinary settings and
node identity/history remain preserved.

## Requirements and troubleshooting

The coordinator needs migration **0017_shared_engine_setup** and this source
revision. All selected computers need the updated worker. Old installers will not
display the tab or appear as compatible wizard participants.

Network inference needs an existing private route between the selected computers.
The wizard does not install Tailscale or change router/firewall rules. Its TLS
listener must be reachable on the selected private address/port. Raw llama.cpp
RPC and the model API bind only to loopback. Do not expose model or RPC endpoints
publicly. Across-location sharing can be much slower than a local model.

The GPU list belongs to the selected runtime backend. CPU-only builds do not
advertise GPUs. Windows/Linux Vulkan needs an already installed compatible
driver; Apple Silicon can use Metal. GPU detection and file presence do not
establish that a model fits in memory or that the architecture is supported.
Only select local models you trust. Threads use the locally approved CPU allowance;
GPU memory and process RAM are not hard OS-enforced limits.

If startup fails, review the owner-local error, model compatibility, free memory,
driver and private route. Refresh, then **Configure and Start** to retry. Reconnect
with a changed credential, changed device selection, or damaged local identity
requires approval again. Administration cannot override an owner's local consent.
Active ordinary attempts keep their fencing and must finish or expire before
the worker can retire that session.

Runtime archives are pinned to upstream **b11846** and verified before use. An
integrity error leaves existing files untouched; repair the affected worker-owned
runtime directory before retrying. Runtime files, public/private identities and
local consents live under `<worker data>/shared-engine/`. Do not share private
keys or consent files. No model paths/private keys are stored centrally.

For a source checkout with the development environment prepared:

```powershell
.venv/Scripts/godfather-worker.exe
```

See [the architecture decision](../decisions/0031-worker-managed-llama-cpp.md)
and [the combined scan/permission changes](worker-scan-and-node-permissions-2026-10-23.md).

## Validation boundaries

Local tests cover persisted approvals, generation fencing, owner isolation,
session retirement, reservations and stopped/revoked group rejection. Real
loopback sockets verify mutual TLS and rejection of an unapproved peer. The
pinned Windows x64 CPU executables were downloaded into the workspace test cache,
checksum verified, and exercised for version/options and actual RPC device
discovery through the mutual TLS bridge. Owned test processes were stopped.
No model weights were downloaded for those checks.

Physical multi-GPU model inference, separate-machine LAN/WAN inference and native
macOS/Linux backend execution still require hardware acceptance. Passing mocked
model/scheduler tests is not evidence of model throughput or hardware compatibility.

Checks executed for this combined pending update:

- Python non-integration suite: **448 passed, 4 skipped**.
- Full disposable-PostgreSQL integration suite: **295 passed**. Two additional
  owner drain/disable cases were then added; the final setup-specific rerun passed
  all **9** tests. Migration upgrade/downgrade and metadata checks passed.
- Dashboard component suite: **44 passed**; ESLint, strict TypeScript, Prettier,
  Ruff formatting/lint and mypy passed. The preceding scan/permission update's
  production dashboard build and management browser smoke also passed.
- Native tab geometry: approval/start/withdraw/progress remain visible at
  **1120×760** and **760×600**. A native wizard fixture exercised installed-model
  and two-computer selection and safely handled closing before its response.
- Real pinned Windows x64 CPU executable version/options and native RPC device
  discovery through the mutual TLS bridge passed. Independent socket tests also
  rejected an unapproved certificate.

No installer build, release/version change, commit, push or deployment was made
for this pending wizard milestone. Ordinary development data was not migrated;
database acceptance used only the explicitly disposable `godfather_test` database.
