# Worker readiness and workspace experience

Owner-authorized scope: in-app worker updates, local Ollama setup, system Overview,
Workspaces directory/detail, self-service account profiles, separate Admin settings,
and distinct Images / Analytics and Reports pages. The owner subsequently authorized
publishing the downloads, deploying Command Center to the VPS, and pushing GitHub.
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
migration gate. The authorized production upgrade applied this migration explicitly;
application startup does not perform migrations.

## Validation

No live VPS or contributor node is modified by local validation.

- Complete local Python/PostgreSQL run: **557 passed, 4 skipped**, using an isolated
  loopback-only `godfather_test` container. The skips cover explicitly optional
  pinned-container checks and Windows symlink support. Final updater/installer
  regressions additionally passed **18 tests**, including hash changes while
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

Recipient automatic-update/Ollama installation and publisher signing remain
unverified. No live installation, enrollment approval, model pull or inference call
was performed on Carbon, Radium or Chromium.

## Published release

Coordinator **0.5.0-rc.2** is prepared at
`dist/godfather-0.5.0-rc.2-linux-amd64.tar.gz`, SHA-256
`d03d46c7c8f50d5ef53c94fda9724d80bee395bf12e74d2f1363deded485a93c`.
It was built from clean source `3269d19ab46d2a081e0cd1668ebaec92531e32f7`.
The final coordinator candidate corrects a loading-state label found in visual
review; a pending worker lookup is not labeled Setup required.

The bundle includes these **0.5.0-rc.1** workers, all built from clean source
`a3d4a3a447aad8fc38572721d116d9caee8ec4ff`. Subsequent worker-related commits
change only test handling of optional Tk on headless runners. The final dashboard
label change does not change worker binaries. Installer hashes were verified before
staging into `dist/worker-downloads-0.5.0-rc.1/`.

| Installer         | SHA-256                                                            |
| ----------------- | ------------------------------------------------------------------ |
| Windows x64       | `06c5ba688c6a0505eab6b0f6de90a78331fb539f7d83548d9dc7376ab54ec2cc` |
| Mac Apple silicon | `38eaca5bab6669aa86eb4bb847b12884fefc1c17f03ed1f616308350c2292dce` |
| Mac Intel         | `4914f91c702085d0ed329b3893cbf770b26de58eb4a99453812619431364d423` |

[Both native Mac jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/39857735346),
including source UI lifecycle, app/DMG/checksum, native library architecture,
ad-hoc signature and real HTTPS unapproved-pairing checks. Those probes cannot
approve enrollment or save a real identity. Windows temporary install/reinstall,
frozen Tk/tray and isolated OS-store checks also passed; its embedded report states
`worker_version: 0.5.0-rc.1` and `stage: passed`.

The final coordinator passed all ten disposable release gates: image identity /
architecture / content, production/Caddy configuration, shell syntax, fresh and
repeat migrations, empty identity bootstrap, private service health, authenticated
HTTP proxy boundaries, complete installer downloads through both hostname routes,
actual database/artifact restore and persistence/restart. Evidence:
`.cache/release-tests/b9cd16e1ba05/result.json`.

The real production Caddyfile separately served `/downloads/ollama.json` through
a loopback-only disposable proxy with the expected six platform artifacts and
pinned version. Evidence: `.cache/readiness-ui/runtime-catalog-http.json`.
Local browser acceptance was repeated after the final navigation/profile changes.
Validation did not use a real Google account or install software on a contributor
host. Isolated local test processes, containers and volumes were removed;
the existing local coordinator was preserved.

The owner-authorized deployment used the normal paired backup and verified release
installer, applied `0015_account_profile`, and restarted the coordinator services.
Existing pre-updater workers require one owner-initiated native installer upgrade.

## Final CI and production activation

[Final source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39859434797)
passed all eight jobs on `3269d19ab46d2a081e0cd1668ebaec92531e32f7`. The real
PostgreSQL/API container suite completed **558 passed, 6 skipped**. Optional
headless Tk/native-library and explicitly optional sandbox checks account for the
container skips; native Windows and Mac UI checks ran separately. Cross-platform
Python 3.12/3.14, dashboard checks/build, database/API restarts and outage recovery,
four independent workers, the 100-job scheduler, lease expiry, inference and
durable-checkpoint interruption/recovery all passed.

The transferred archive matched its trusted local SHA-256 before extraction.
Production now points to
`/opt/the-godfather/releases/godfather-0.5.0-rc.2-linux-amd64`; API metadata confirms
the exact version/source and migration `0015_account_profile`. All five services
are healthy. Only Caddy publishes host ports; database, Redis, API and dashboard
ports remain private. Four workers reconnected online, with no active jobs at
upgrade or postflight.

The production environment remained byte-identical with mode 600. Fingerprints
matched for 2 users (excluding only the newly added profile column), 2 Google
identities, 3 workspaces, 1 membership, 6 credentials, 4 node ownership/policy
records, 12 jobs, 7 agents, 6 artifacts, 3 checkpoints, 3 provider connections
and 1 encrypted account key. No key was decrypted or contributor host reconfigured.

Paired backup: `/opt/the-godfather/state/backups/20261022T215705-1320805`.
Checksums, PostgreSQL dump listing and artifact archive integrity passed.
Restore tests used the disposable release environment; production was not restored.
Previous releases/downloads are retained.

Ignored local deployment evidence: `.cache/readiness-deployment-2026-10-22/`.
Server-side preservation evidence:
`/opt/the-godfather/state/deployments/readiness-20261022-rc2`.

All **60 public HTTP checks passed** through normal DNS and verified TLS. All
three installers returned HTTP 200 with exact SHA-256 matches on both hostnames
(six full download/hash checks). Both runtime catalogs exactly match the pinned
release catalog. New account/workspace/workload pages redirect anonymous users to
sign-in; profile operations, private APIs and worker operations reject unauthenticated
or foreign-origin requests. These probes created no accounts, jobs or enrollments.

Actual recipient sign-in, in-app update, Ollama setup and model inference remain
physical acceptance tasks. Coordinator deployment does not install workers or grant
new host permissions on Carbon, Radium, Chromium or another contributor's computer.
No later milestone was started.
