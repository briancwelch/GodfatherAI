# Phase 12: images, analytics and reports

The owner authorized implementation/build/deployment and required a GitHub main
checkpoint first. That checkpoint is `5f375637e0a8c80bafdf27c5c84de9e6ab7567ce`.
The owner subsequently confirmed that **no real dataset is authorized yet**.
Acceptance uses deterministic fixtures only in isolated tests; production must not
receive fictional datasets or test jobs. Owners may submit their own datasets to
any compatible, permitted worker. No paid image request is authorized.

## Use the Command Center

Open **Images / Analytics / Reports**, choose an authorized workspace and workload.
Upload a CSV, JSON or values-only Excel workbook, enter the request/context and
optionally select grouping, ISO date and numeric value columns by their exact names.
The calculations are deterministic: the request is context, not generated code.
Submit Analytics only or Analytics → report. The latter checkpoints completed
analysis before reporting; recovery skips the committed stage.

Job detail shows calculated statistics, group/month charts, period comparisons,
source checksum and downloads before technical details. History, cancellation,
retry, checkpoints and failover use existing Jobs. Reports are HTML (including a
chart), Markdown, CSV or Excel; each report also provides structured analysis JSON.
PDF is not implemented. CSV/Excel reports include source, checksum, summary and
methodology. Spreadsheet exports use strings and neutralize formula prefixes.

Uploads are bounded to 1 MiB, 10,000 records and 64 columns. UTF-8 CSV needs a header
and consistent row widths. JSON accepts flat record arrays or an authorized SQL
export shaped as `{"columns":["name"],"rows":[["value"]]}`. No database SQL is
executed. Excel reads `xl/worksheets/sheet1.xml` only, rejects formulas, macros and
external links, and bounds ZIP expansion to 8 MiB/200 entries. Date columns must
contain ISO values (Excel date serials must be exported as ISO strings). Nested
records, complex workbooks and larger datasets need a bounded export first.

Numeric columns require finite numeric nonmissing values. Missing values are
excluded and counted. Statistics include count, missing count, sum, mean, median,
min/max and sample standard deviation. Anomaly candidates use absolute z-score
greater than 3; this is a transparent heuristic, not a significance/causality claim.
Groups/months are limited to 100. Monthly changes compare observed periods; absent
months are not silently synthesized, and percentage changes from zero are unknown.

Google Sign-In authorizes identity only. Google Sheets/Drive account ingestion and
live SQL source connections are **not configured/implemented** in this candidate.
Export an authorized spreadsheet and upload it. A future Google data connection
needs separate read-only consent, encrypted refresh credentials, revocation and
workspace/worker restrictions; do not reuse Google login tokens or change Google
Cloud settings under this assignment. No real data-connection credentials exist.

## Owner-controlled worker setup

Updated Consigliere Settings contains optional data sandbox and local image backend
configuration. Blank values disable these capabilities. The owner must already
have a local Docker engine and a pinned image containing Python 3.12+ standard
library. No image/model/dependency download, service installation or Docker endpoint
change occurs. Enter the existing image digest to allow analytics/report execution.
Saving opts this computer into these workloads; Pause, change Settings, then Resume.
Existing credentials, node identity, contributions and private project grants remain.

CLI users may create owner-local `workloads.json`:

```json
{
  "image": "sha256:REPLACE_WITH_EXISTING_LOCAL_IMAGE_ID",
  "images": null
}
```

The placeholder is intentionally invalid. Inspect an already installed suitable
image with `docker image inspect --format '{{.Id}}' YOUR_EXISTING_IMAGE`. Its identity
must be a SHA-256 ID or digest; `--pull=never` prevents automatic retrieval. Start
the existing authenticated worker with:

```text
godfather-worker-cli --url YOUR_CONFIGURED_COORDINATOR --credential-file YOUR_EXISTING_WORKER_CREDENTIAL --execute-workflows --workload-config workloads.json --allow-tool-permission data.analyze
```

Do not create another node identity just to enable a workload. Native Windows,
macOS and Linux use the same Python workflow core and a local Linux-container
adapter; absent Docker/image support is an honest unavailable state. A reporting
worker can also analyze; schedules require both capabilities for the combined job.

## Optional local images

The model gateway now has a separate extensible image adapter protocol. The first
adapter is an already installed AUTOMATIC1111 API on literal loopback HTTP, with
an owner-configured allowlist of installed `model_name` values. It discovers actual
models before advertising; it never treats Ollama text models as image providers.

```json
{
  "image": null,
  "images": {
    "backend": "automatic1111",
    "url": "http://127.0.0.1:7860",
    "models": ["EXACT_INSTALLED_MODEL_NAME"]
  }
}
```

Grant `images.generate` in the CLI or save these explicit local settings in the
desktop. Configure an existing dedicated backend; this release does not install or
launch one. Supported controls: 256–1024 pixels in 64-pixel increments, 1–4 images,
1–50 sampling steps and seed (-1 requests random). Output is validated/re-encoded
PNG. Metadata describes the prompt and requested settings, not an invented actual
random seed. No credentials are sent and there is no cloud fallback. Cloud image
providers must later implement the existing account/provider authorization before
use; they cannot be configured through this local adapter.

Image jobs have no automatic replay. Cancellation closes the request and fences
publication; an already accepted local generation may finish on its backend.
The adapter avoids a global interrupt that could cancel unrelated backend work.
The [official API guide](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API)
documents discovery and generation; inspect the installed backend's `/docs` for its
actual version. No configured image provider means live image acceptance is pending.

## Isolation, artifacts and recovery

The existing sequential agent runtime, PostgreSQL job/attempt state machine,
resource matching, fair scheduling, node-owner/workspace policy, leases/fencing and
immutable versioned artifacts remain authoritative. There is no second scheduler.
Data workflows explicitly omit text-model selection; legacy assignments retain
their wire shape, and new stages require separately advertised runtimes/permissions.

Fixed repository code parses data in an unprivileged, networkless, read-only-root
container, with one CPU, 512 MiB memory/swap ceiling, 32 PIDs, 16 MiB temporary
storage and bounded stdout/time. Its only host mount is a private temporary copy of
the fixed program and submitted JSON, read-only. No generated Python, generated SQL,
host shell, source repository, Docker socket or provider credentials enter it.
Cancellation/timeout removes only that generated disposable container. The local
Docker engine itself remains owner-trusted, as with coding execution.

Source uploads persist in the PostgreSQL job input before assignment; disconnection
cannot lose the submitted dataset. Completed analysis/report/image envelopes use
the existing centrally durable artifact store, fsync-before-reference, immutable
UUID names and SHA-256 verification. The additive `0012_workload_artifacts` migration
raises the bounded envelope limit to 8 MiB; rollback refuses larger records rather
than truncating them. No tables/data are removed. Only workflow checkpoint writes
gain a 9 MiB public request bound; ordinary routes retain 2 MiB. Worker poll/artifact
reads support the larger bounded envelopes. Workspace authorization and integrity
are rechecked on every file download, including after restart. HTML downloads are
attachments with restrictive CSP; generated HTML is never injected into the app.

## Validation and remaining acceptance

Run native formatting/lint/mypy/pytest and dashboard checks, then the real PostgreSQL
suite against `godfather_test` only. `tests/test_workloads.py` includes an opt-in
real sandbox test using `GODFATHER_CODING_TEST_IMAGE` set to an **existing** local
image digest. Integration tests cover prefix recovery, stale fencing, restart,
download authorization, input contracts and withdrawn node-owner permission.

Deployment and actual executed results are recorded separately after validation.
Real customer analytics/reporting acceptance awaits an owner-submitted authorized
dataset. No fictional production records or paid/live image calls may be created
to manufacture acceptance. Cross-platform packaging is evidence of native builds,
not proof of physical Docker/inference performance on every recipient computer.

## UI acceptance checklist

The new navigation section lets users select a workspace, upload and submit data,
choose output formats, see honest worker/provider availability and open job history.
It reuses compact application chrome, panel/form controls and responsive field grids.
Loading, no workspace, no compatible worker/provider, rejected input and submission
failure states are explicit; labels, keyboard focus and status live regions remain.
Data comes from authenticated workspace options/submission and persisted job outputs.
Browser tests must cover upload-to-job navigation, unavailable images, readable
tables/charts, download links and narrow viewport layout. Technical diagnostics
remain in existing Job detail disclosure.
