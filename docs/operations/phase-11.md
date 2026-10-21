# Phase 11: coding, results and independent provider connections

The user explicitly authorized this assignment, including routine deployment to the
existing environment. This supersedes earlier planning-only BYOK notes. No frontier
credentials or billable calls have been authorized or supplied. The user separately
approved SSH access and deployment of `0.2.0-rc.4`; the upgrade and preservation
checks passed. See [deployment verification](phase-11-deployment-2026-10-20.md)
for executed checks and remaining live coding/provider acceptance.

## Identity and billing

**Current usability revision:** the owner subsequently authorized encrypted
account key entry and provider-managed billing on 2026-10-21. For candidate
`0.3.1-rc.2`, follow [account connections and project setup](coding-and-account-setup.md).
The local-key commands and spending-policy instructions below document the legacy
compatible path; they are not required by the new account flow.

Google OIDC remains the account/session system, with the existing invitation and
workspace RBAC checks. Its tokens, scopes and client secret are not provider API
credentials. OpenAI Responses and Anthropic Messages use separate, owner-local API
keys. Consumer ChatGPT/Claude subscriptions and browser tokens are not supported.
Node machine authentication remains independent of both systems.

Open **Provider Connections**, choose a provider and an owned worker, and create a
private connection. Creation stores metadata only and leaves spending disabled.
On that worker, under the owner's OS account, run:

```text
godfather-worker provider set openai CONNECTION_UUID
godfather-worker provider set anthropic CONNECTION_UUID
```

The command prompts without echo and stores the key in Windows Credential Manager,
macOS Keychain or Linux Secret Service. There is no plaintext fallback or central
key-upload endpoint. A missing/locked/unsupported store fails closed; headless Linux
requires an already configured supported Secret Service. This feature installs no
OS services. The pip installation also exposes `godfather-worker-provider`.

Add the public connection reference to the worker's existing provider JSON:

```json
[
  { "id": "local", "provider": "ollama", "url": "http://127.0.0.1:11434" },
  {
    "id": "my-api",
    "provider": "openai",
    "connection_id": "CONNECTION_UUID",
    "model_catalog": [
      {
        "identifier": "EXACT_PROVIDER_MODEL_ID",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "tools": false,
        "structured_output": false
      }
    ]
  }
]
```

Replace all placeholders and verify each model's actual limits/operations using
the provider's current documentation. The numbers above illustrate configuration,
not a model capability claim. Use `anthropic` for Messages. Native endpoints are
fixed to official HTTPS APIs. The
official OpenAI/Anthropic hosts cannot be configured through the legacy compatible
adapter to bypass connection policy. Existing local Ollama/compatible runtimes stay
available. Listing an ID does not certify feature support; the
owner must enable supported operations individually. Catalogs are intersected with
actual provider discovery; unavailable IDs are not advertised. Discovery and Test
Connection list models without running inference. They still require a valid key.

In Provider Connections, enter owner-verified documented input/output prices in USD
per million tokens, official source URLs and verification dates. Verification expires
after 30 days. Unknown/stale pricing blocks paid reservations. Enable a connection
only after setting per-call and lifetime safeguards. Set a default model and select
the exact permitted provider connection/model when creating an agent. Each paid run
requires a separate submitter confirmation covering spending and task data egress.

Private connections can serve only their owner. Sharing additionally needs explicit
borrower/workspace allowlists and an owner-issued expiring model grant. Per-job
approval requires the exact pending job ID; issuing it binds the grant to that job.
Node-owner contribution permissions and workspace model policies still apply.
Neither Google sign-in nor platform administration bypasses these checks.

PostgreSQL records the payer, submitter, job, attempt, connection, reservation,
price version and provider-reported token counts. Costs are integer micro-USD
estimates, not invoices. Concurrent reservations consume the same connection/grant
allowance. Missing usage retains its reservation for reconciliation. Usage with
cache-pricing categories unsupported by this initial base-token estimator also
requires reconciliation rather than inventing a settled cost. Paid retries
and paid fallback are disabled; a possibly accepted external call is not replayed.
Application limits cannot guarantee provider billing caps.

Disable/revoke blocks future authorizations without changing Google login, sessions
or node ownership. Already authorized external requests may still incur charges.
Revoke the actual key at its provider separately. Remove the local stored copy with:

```text
godfather-worker provider delete openai CONNECTION_UUID
```

## Coding worker opt-in

Coding reuses Phase 06's sequential workflow, immutable artifacts and fenced
checkpoints. Start with one `coding` step, `output_schema=coding`, explicit
`coding.workspace` permission, `coding-sandbox-v1` runtime and zero automatic
retries. The UI creates this definition through the Coding workflow option.

The node owner supplies a local repository JSON configuration with these fields:

```json
[
  {
    "id": "REPOSITORY_UUID",
    "name": "Approved project",
    "path": "ABSOLUTE_LOCAL_REPOSITORY_PATH",
    "image": "sha256:EXISTING_LOCAL_IMAGE_ID",
    "allowed_user_ids": ["USER_UUID"],
    "allowed_workspace_ids": ["WORKSPACE_UUID"],
    "files": ["src/*.py", "tests/*.py"],
    "commands": [["python", "-m", "unittest", "discover", "-s", "tests"]]
  }
]
```

Use an already installed Linux toolchain image, pinned by image ID or repository
digest. It must contain `/bin/sh`, `cp` and the approved test/build tools and offline
dependencies. No image/model downloads or dependency installation are automatic.
Start the existing worker with its existing machine credential and inference
configuration, adding:

```text
--execute-workflows --coding-config coding.json --allow-tool-permission coding.workspace
```

Select that advertised repository when submitting a coding task. Optional literal
code-search terms return up to 32 matching file/line references and feed those
actual matches to the agent. Only committed
UTF-8 text files matching the owner's bounded patterns enter the snapshot. Git
metadata, credential directories, environment files, symlinks and unsafe paths are
excluded or refused. This first implementation bounds the repository prompt to
32,768 characters and outputs to the existing artifact limits; select a focused
set of files for larger repositories. It does not inspect uncommitted source work.

The worker inspects the approved snapshot, requests a bounded edit plan, validates
every edit and executes only owner-configured commands. Tests run as an unprivileged
UID in a networkless, read-only-root Linux container, with no host credentials or
Docker socket. The host snapshot is read-only; the writable test workspace is a
256 MiB tmpfs and `/tmp` is 64 MiB. Test writes are disposable and do not amend the
proposed patch. CPU, memory, process count, output and time are bounded. Remote
Docker endpoints are refused. Docker itself remains an owner-trusted local service.

The deliverable contains the source commit, actual Git diff, changed files and
actual command exit codes/output. Failing tests are explicitly reported; completed
job status means the deliverable was produced, not that every test passed. The
original repository is preserved. Git pushes, deployment, host shell tools and
destructive operations are absent. A lost coding attempt requires review rather
than replaying commands. Committed artifacts remain portable and authorized by
workspace. The worker protocol retains its existing local-inference wire shape;
new coding assignments require separately advertised capabilities.

## Results and release status

Job detail prioritizes sanitized Markdown, highlighted code/diffs, readable JSON,
tables, chart data and supported authorized document/media envelopes. Copy and
download controls use persisted output; artifact downloads recheck workspace access
and integrity. Remote Markdown images and raw HTML are not rendered. Partial output
is labeled; cancellation continues to clear private stream output. Raw results,
attempts, checkpoints and lifecycle/failover events remain in Technical Details.
No image/report generation subsystem is added by the result renderers themselves.

The status bar reads version, Git revision and build timestamp embedded by
`scripts.release`; environment comes from the running API configuration. Local
development with no release metadata says unavailable. Nothing hardcodes the
currently deployed release into the dashboard.

## Validation

Run normal Ruff, mypy, pytest, frontend lint/typecheck/tests/build and the disposable
PostgreSQL suite as documented in setup. Real worker/container/browser acceptance:

```powershell
$codingImage = docker image inspect --format '{{.Id}}' godfather-local-api
.venv/Scripts/python.exe -m scripts.check_google_oidc --model EXISTING_OLLAMA_MODEL --coding-image $codingImage
```

This uses real PostgreSQL, native Windows worker, installed local model, Git and
Docker, with Google network responses mocked only inside the isolated OIDC test
server. It resets only `godfather_test`. Run serially after database tests.
Physical macOS/Linux workers, real Google login after upgrade, real paid-provider
calls, production data preservation and deployed version checks need their actual
environments. Do not treat mocks or local evidence as live acceptance.

Provider references: [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses),
[OpenAI structured output](https://developers.openai.com/api/docs/guides/structured-outputs),
[Claude Messages](https://platform.claude.com/docs/en/claude_api_primer),
[Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming).
