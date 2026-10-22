# Worker readiness and workspace experience

Owner-authorized scope: in-app worker updates, local Ollama setup, system Overview,
Workspaces directory/detail, self-service account profiles, separate Admin settings,
and distinct Images / Analytics and Reports pages. No deployment is authorized.
Worker-side job submission is explicitly excluded.

## Using the changes

1. Upgrade an older Consigliere once with the new native installer. Builds before
   this milestone cannot acquire an updater by themselves. Existing identity,
   ownership, projects, settings and OS-store credentials are retained.
2. Nodes displays **Update Available** beside older reported versions. Unknown
   versions and newer/source builds are not mislabeled. The catalog refreshes
   every minute. The desktop checks after connection and every 30 minutes; File
   > Check for updates also checks on demand.
3. Accept the desktop prompt, or opt into **Settings > General > Install verified
   worker updates automatically when idle**. Downloads are SHA-256 checked. The
   worker finishes an assigned attempt before the installer starts, rather than
   cancelling it. Installer failures preserve the existing app where replacement
   has not completed; app replacement uses its existing rollback staging.
4. On a newly connected worker, open **Models & API connections > Get started ·
   Download local model from Command Center**. Approve this computer's network,
   storage, local-model and runtime-setup permissions. After Ollama becomes ready,
   the app opens **Models > Add / use model > Download local model**. Choose the
   owned worker and a catalog model, confirm, and follow the durable job progress.
   After completion, choose **Use installed model in this workspace** to grant
   workspace model access and create an agent through the existing flow.
5. Alternatively, enable local models, model downloads and Ollama runtime setup
   separately under **Settings > Resources**, then resume. Command Center offers
   **Install or start Ollama on this worker if needed** for opted-in workers.
   Without that local consent, setup cannot be requested remotely.
6. **Overview** summarizes accessible workspaces. Create a workspace directly there
   or on **Workspaces**, then open its scoped overview. Private workspaces remain
   invisible to other administrators. Jobs/Agents/Models navigation retains scope.
7. **Account settings** lets every invited account edit its display name, HTTPS
   avatar image address and optional location, and links to personal AI connections.
   Leaving the avatar blank uses Godfather initials. Custom profiles survive Google
   sign-in. **Admin settings** is shown only to platform administrators.
8. **Images** and **Analytics and Reports** now have separate routes. Their worker
   setup panel starts expanded on the right, collapses to a slim rail, and stacks
   on narrow displays. These workflows still require their existing local image
   backend / isolated data sandbox; Ollama text models do not provide those tools.

## Runtime catalog and boundaries

`infrastructure/ollama-runtimes.json` pins official Ollama 0.40.8 artifacts using
the SHA-256 digests returned by the official GitHub release API. The coordinator
release copies it to `/downloads/ollama.json`. Artifacts are downloaded directly
from the official GitHub release/CDN, verified, and extracted to the worker's local
data folder. No system service, PATH change or elevated installer is used. Existing
running Ollama is reused. Managed Ollama starts only on `127.0.0.1:11434`.

References: [Ollama Windows](https://docs.ollama.com/windows),
[Ollama Linux](https://docs.ollama.com/linux),
[pinned official release metadata](https://api.github.com/repos/ollama/ollama/releases/tags/v0.40.8).

Portable Linux provisioning requires Python 3.14 for the upstream zstd archive;
older Python workers can retain a manually installed Ollama. A generic CPU/runtime
package is not a guarantee of GPU acceleration or identical model performance.
Native signing and actual recipient update/setup acceptance remain separate gates.
Hashes establish integrity relative to the trusted coordinator's catalog; they do
not substitute for publisher signing or protect a compromised coordinator.

Migration head is `0015_account_profile`. Apply it through the normal release
migration gate; no startup migration or production schema change is performed by
this development milestone.

## Validation

No live VPS or contributor node is modified by local validation.

- Complete local Python/PostgreSQL run: **557 passed, 4 skipped**, using an isolated
  loopback-only `godfather_test` container. The skips cover explicitly optional
  pinned-container checks and Windows symlink support. Final updater/installer
  regressions additionally passed **17 tests**, including hash changes while
  waiting, absent catalogs, default prompting, separate runtime consent, archive
  traversal and graceful completion of an in-flight claim.
- Full integration-only run: **234 passed**. The final profile/relogin and model
  installation group passed **7 tests**, including custom profile persistence
  through Google sign-in and separately opted-in, node-pinned runtime setup.
- **29 dashboard component tests passed**. Ruff format/lint, strict mypy, ESLint,
  strict TypeScript and the production Next.js build passed before packaging.
- Actual native Windows Tk/tray lifecycle passed both fresh and saved synthetic
  connection scenarios. A delayed update callback found during this check was
  fixed and the native check repeated without the Tk shutdown error.
- Local Edge/Playwright with real PostgreSQL/FastAPI and test-only Google HTTP
  verified workspace creation/directory/scoped navigation, global Overview,
  persisted profiles, separate workloads, panel collapse/expand, member account
  access and denial of Admin settings. No page errors were recorded.
- The real pinned macOS Ollama archive was downloaded into project cache and its
  SHA-256 matched. Its 59 entries include safe relative library symlinks; those
  are supported with tar's data filter. This is archive compatibility evidence,
  not physical Mac installation, inference or GPU validation.
- Browser captures are under `.cache/readiness-ui/`: `overview.png`,
  `workspaces.png`, `account.png`, `images.png`, `analytics.png` and
  `analytics-narrow.png`. Native capture: `worker-connection.png`.

Candidate build/release results will be appended after native packaging. Recipient
automatic-update/Ollama installation and publisher signing remain unverified.
