# Local model scan, node registration permissions and worker feedback

Published in **0.10.0-rc.3**, 2026-10-24, after the owner's separate release
authorization. See [release verification](shared-inference-release-2026-10-24.md).
The release also includes [managed llama.cpp setup in the Shared Inference
tab](shared-inference-wizard-2026-10-23.md), with local device approvals on every
participating computer.

## Scan this computer

In Consigliere, open **Models & API connections → Scan for Local Models**.
Results appear in the **Local model scan** tab. Scanning never starts
automatically on opening the app. Previously permitted provider connections
continue their normal inventory refresh when the worker runs.

The scan checks standard Ollama, LM Studio, Hugging Face, GPT4All, Jan, and
ComfyUI/AUTOMATIC1111 model directories; common local `Models`/`AI` folders;
Downloads; and configured `OLLAMA_MODELS`, `HF_HOME`, `HF_HUB_CACHE`,
`HUGGINGFACE_HUB_CACHE`, `TRANSFORMERS_CACHE` and `JAN_DATA_FOLDER` locations.
It recognizes GGUF/GGML, SafeTensors, common PyTorch BIN weights, CKPT, PT/PTH,
ONNX, H5/HDF5, Keras, TFLite and Core ML files/bundles. It also checks conventional
Whisper/Torch caches and readable Linux system Ollama/image-model directories.
Shards and snapshot tensors are grouped where the
format/layout provides evidence of one model. File presence does not certify
complete weights, compatibility or inference performance.

Use **Add folder…** for other drives or custom installations. Select a parent
folder to search its supported model files recursively. Use **Add local
server…** for a nonstandard OpenAI-compatible port. Default probes use loopback
Ollama port 11434 and OpenAI-compatible ports 1234, 4891, 1337, 8080, 8000 and 5001. Custom and saved server choices take priority within eight total
connections. The scan does not start these servers or use API keys. A server
requiring authentication needs separate manual configuration.

**Local server** means the endpoint reported the model. **Files · runtime
unverified** means files were found, and a compatible runtime/server still needs
to expose the model before Godfather can schedule inference. Image files remain
subject to the existing image-workload setup and permissions.

**Use detected local text servers** is a separate owner action. It enables local
model use and saves discovered OpenAI-compatible text servers for chat/streaming;
it preserves previously configured servers when they fit the limit. If the combined
list would exceed seven text servers plus Ollama, the owner chooses whether to
replace the saved text-server list with the detected servers. Existing work finishes before the
worker re-registers. This does not enable downloads, account API connections,
host tools or new workspace permissions. File locations remain local.

At most **128 results** are shown. Extra results are counted, not advertised
beyond the protocol limit. Combined runnable deployment advertisements also
remain capped at 128. The scan reports skipped unreadable items and cancellation
or search limits. For a very large library, select a narrower folder and retry.
Folders/ports added to a scan are session choices; enabled server connections
are saved in owner-local contribution settings. Arbitrary proprietary or
inaccessible installations cannot be guaranteed discoverable.

## Choose who may add computers

Platform administrators open **Admin settings → Node permissions**:

- **Members can add nodes** controls new member-owned computers.
- **Contributors can add nodes** controls new contributor-owned computers.
- Switch both off for administrator-only new-node registration.

Both switches start enabled to preserve existing behavior. Save the changes to
apply them immediately through the backend. The UI reports pending, failure and
confirmed success, and the audit log records the change. An account with multiple
roles may add nodes if any assigned role allows it. Administrators always retain
the ability to add their own computers.

Existing nodes keep connecting and contributing; restrictions apply to new
computers, including pending pairings and credentials that have not registered
a computer yet. Owners may still reconnect an existing registered computer with
its exact name and history. The old worker must be offline and its unfinished
work settled. Local host permissions and workspace membership remain separate.

The pairing page now warns immediately below **Reconnect this computer** to use
that option only for an existing node whose name and job history should be kept.
It remains unchecked for a new connection. Restricted users must explicitly
select Reconnect before approving an existing node.

## Update and connection feedback

**File → Check for updates** immediately displays **Checking for updates…** and
an animated progress bar beside the bottom connection status. Progress is
indeterminate because the catalog request has no measurable completion
percentage. It stops on completion/failure; download progress uses the same
indicator. Disconnected/source-checkout states explain why updates are unavailable.

A small lock appears to the left of **Connected** only after an authenticated
registration or heartbeat succeeds through certificate-verified HTTPS. It clears
when the worker pauses, disconnects, is refused/disabled, or reports a session
conflict/failure. Local development HTTP connections show no lock. A saved
connection or optional Tailscale connection alone never enables it.

## Validation

Local verification completed on 2026-10-23:

- **416 Python tests passed**, four existing environment skips, with 288
  integration tests deselected from that native run. The skips require an
  explicitly selected sandbox image or host symlink privileges.
- **103 PostgreSQL integration tests passed**: 25 policy/enrollment tests and
  78 existing authentication, administration, node and contribution tests.
- **44 dashboard component tests passed**. Isolated Edge browser acceptance
  passed for role switches, failed-save retry, persisted settings, the reconnect
  warning and restricted-member flow, plus existing management scenarios.
  Desktop/mobile screenshots are under `.cache/command-center-management/`.
- Native Tk widget checks passed across Connection, Models and scan tabs at
  1120×760 and 760×600. The progress bar and secure icon remained mapped and
  connection text retained space. These were geometry checks; native screenshot
  capture did not provide valid application images and is not claimed as visual
  acceptance. Results are in `.cache/worker-scan-permissions/native-result.json`.
- Ruff formatting/lint, strict mypy, dashboard ESLint, TypeScript checking,
  Prettier, dashboard production compilation and `git diff --check` passed.

The first broad run found two fixtures needing the new permission/lock fields;
these were corrected. An unchanged Windows installer test also returned one
access-denied error; its isolated retry and final full native suite passed
without changing installer code. The older browser harness expected the retired
Out of Date badge text; it now asserts the existing Update Available wording.

Reproduce the native and component checks with:

```text
.venv/Scripts/python.exe -m pytest -m "not integration" -q -r f
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
node tests/e2e/command-center-management.cjs
```

Integration used the existing local `api-test` image with the changed source
mounted read-only and the explicitly disposable `godfather_test` database.
Fixtures apply/revert migrations only to that test database. Tests use synthetic
model files, metadata endpoints and accounts; Google's upstream exchange is
mocked. Actual host libraries, inference, new installers, real accounts and
physical macOS/Linux discovery were not validated. No live account, provider
inference, production setting, installer or deployment was changed.

Implementation files are grouped as follows:

- Worker discovery and feedback: `local_model_scan.py`, `discovery.py`,
  `desktop.py`, `desktop_app.py` and `inference.py` in `packages/worker`.
- Gateway selection/limits: `ProviderConfig` and provider discovery in
  `packages/model-gateway`.
- Backend policy: `node_registration.py`, authentication account responses,
  enrollment, manual credential issuance and first registration in `apps/api`.
- Dashboard: `node-registration-settings.tsx`, Administration tabs, worker
  enrollment, the allowlisted control bridge and switch sizing.
- Regression tests and the linked decision/operating guides.

No dependency, database schema, worker protocol or release version changed.
Work remains uncommitted in the local working tree while publishing is on hold.

See [the design decision](../decisions/0030-local-model-scan-and-node-registration-policy.md).
