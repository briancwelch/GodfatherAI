# Owner-approved model installation through durable jobs

The user authorized selecting and installing models on owned workers as part of
the Command Center assignment. Extend the existing scheduler with `model.install`,
not a second execution system. No database migration is required.

Only the authenticated node owner may submit a confirmed catalog download. A
worker must advertise `model.install.v1` and its local Ollama provider alias after
being started with `--allow-model-installation`. Older workers receive no install
jobs. Neither another administrator nor a workspace administrator can substitute
for the node owner. The local provider configuration remains private.

Desktop usability correction (2026-10-21): Consigliere exposes a separate
**Allow model downloads from Command Center** opt-in under Models & API connections
and Settings → Resources. It defaults to false for new and existing settings and
passes the same `--allow-model-installation` flag to the existing CLI. Local-model
use must also be enabled. Empty installed-model inventories may connect so the
first catalog model can be downloaded. Changes require Pause and Resume; each
download still requires the existing owner-only Command Center confirmation.

Each installation is pinned to its approved node/provider/model, has a one-hour
deadline, normal leases/fencing, bounded streamed progress, and zero automatic
retries. Ollama pulls content-addressed layers; cancellation does not promise
removal of cached data or reversal of completed side effects. Duplicate active
requests are refused under the node transaction lock. Completion requires a
successful pull and subsequent model discovery. Inventory is re-advertised before
the worker takes another job. A 16 GiB per-model reported-layer safeguard is not
a guarantee of free disk space or a total storage quota.

The initial download catalog lists explicit public Ollama tags; it is separate
from authenticated installed-model inventory. No cloud provider, billing path,
automatic runtime installation, arbitrary URL, shell or model deletion is added.
The catalog can be extended after reviewing additional model sources and licenses.

Reference: [Ollama pull API](https://docs.ollama.com/api/pull),
[Qwen 3](https://ollama.com/library/qwen3),
[Llama 3.2](https://ollama.com/library/llama3.2).
