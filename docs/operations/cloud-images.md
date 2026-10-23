# Cloud images

Published in coordinator and Consigliere **0.9.0-rc.1** on 2026-10-23. See the
[release verification](cloud-images-deployment-2026-10-23.md) for packaging and live
checks. Local AUTOMATIC1111 instructions remain in the [Phase 12 history](../history/phases.md#phase-12).

## Setup and use

1. Open **AI connections** in your account. Add an OpenAI or Google Gemini API key
   and select the owned computer permitted to use it. If OpenAI is already
   connected, enter and save the key again to refresh its image-model catalog.
   Google sign-in does not provide a Gemini API key.
2. Pause that computer in Consigliere. Open **Settings > Resources**, enable
   **Use API connections authorized for this computer**, then under **Workloads**
   enable **Allow cloud image generation with my account API connections**.
   Save and resume. These permissions default to off for existing installations.
3. Open **Images** in Command Center. Choose your workspace, provider, and an
   advertised model/computer from **My cloud model and computer**. Models appear
   after the worker refreshes its provider inventory, normally within 30 seconds.
   Workspace administrators must allow the model if that workspace restricts models.
4. Enter the image prompt. Confirm sending it to the named provider using your
   API connection and accepting provider charges. Choose **Run workload**.
5. Open the job to inspect the resulting image and download its PNG. Job state,
   checkpoints and files are stored durably using the existing artifact path.

Cloud jobs generate one 1024 x 1024 PNG. The provider controls quality, account
access and billing. Godfather currently uses medium quality for OpenAI and square
native generation for Gemini. Local sampling steps and seeds do not apply to
cloud images. Your worker needs outbound HTTPS and its existing authenticated
connection; a local image model, GPU and Docker are unnecessary for cloud images.

OpenAI GPT Image and reviewed Gemini image model IDs are offered only when the
provider lists them for your key. Model listing does not prove generation access;
provider account verification, billing or quotas may still block a generation.
Anthropic remains available for its existing text workflows.

## Source/CLI worker

Keep the existing worker identity and its private credential file. From a prepared
source checkout, run this command with your configured coordinator address and
existing credential path:

```text
uv run --locked --all-packages godfather-worker --url https://YOUR-COMMAND-CENTER --credential-file PATH-TO-EXISTING-WORKER-CREDENTIAL.json --account-providers --cloud-images --execute-workflows --allow-tool-permission images.generate
```

Do not put a provider key in CLI arguments or the credential file. It remains in
your account vault and is delivered to the selected worker in memory. CLI cloud
execution is restricted to a physical, opted-in worker. It does not install tools
or enable model downloads.

## Failures and recovery

- **No compatible worker/model:** check worker version, connection, both local
  opt-ins, selected computer grants and workspace model permissions. Old workers
  receive text catalogs only. No local/cloud fallback is performed.
- **Authentication, rate limit or model unavailable:** inspect your provider's
  account configuration. The job reports a redacted error without provider keys
  or raw provider error bodies.
- **Timeout/disconnect/cancellation:** the provider may already have accepted and
  charged for the request. Godfather retains a durable invocation marker and
  does not automatically repeat it. Review the provider's records before
  submitting a separately authorized new job.
- **Unexpected output:** oversized, malformed, non-PNG or wrong-dimension images
  are rejected. No URL returned by a provider is followed. An accepted generation
  may still be billable even if its output cannot be delivered.

Revoking the account connection, removing its computer grant, disabling account
API access or cloud image permission blocks new calls. An already accepted
provider operation can finish. Your provider handles spending limits; recorded
token usage is informational and is not a provider invoice.

See the [architecture decision](../decisions/0027-cloud-image-providers.md) for
the authorization, replay and backward compatibility boundaries.

## Implementation verification, 2026-10-22

- Windows Python unit suite: **362 passed, 4 skipped**. Skips require an explicitly
  selected local coding/data sandbox image or host symlink permission.
- Full PostgreSQL integration suite: **279 passed** in the existing Linux test
  container, using current source mounts and the disposable `godfather_test`
  database. Normal development and production databases were not reset.
- Dashboard component regressions: **42 passed**. Strict TypeScript, ESLint,
  Prettier, Ruff formatting/lint and strict mypy checks passed. The optimized
  dashboard build passed locally.
- New checks exercise both native image request/response formats, image-only
  catalogs, owner consent, older worker filtering, per-computer opt-in,
  revocation, duplicate-call refusal, unavailable-worker queuing, durable PNG
  downloads, redaction, output bounds, timeout and cancellation behavior.

Provider HTTP was mocked. No provider key was read from a real account and no
billable generation was made. Physical macOS/Linux worker acceptance, new desktop
installers, release packaging, production deployment and live account/model
acceptance were not performed in this implementation milestone.
