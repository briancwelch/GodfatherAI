# Project cleanup - October 22, 2026

Owner-authorized maintenance of the local project, GitHub branches and existing VPS. No new
feature phase, deployment, paid inference or worker reconfiguration is included.

## Retention

Keep the current working release and five predecessors separately for the
coordinator and each worker platform. Use release versions, not filesystem times.
Preserve package checksums, manifests and matching installers with retained builds.
Never remove a running container's configured image, persistent volumes, private
configuration, credentials, backups, owner workspaces or source regression tests
as a cache cleanup. Older image tags do not guarantee a safe database rollback.

| Family                                                     | Retained versions (newest first)                                       |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| Coordinator archives, extracted bundles and release images | 0.8.0-rc.1, 0.7.0-rc.2, 0.7.0-rc.1, 0.6.0-rc.2, 0.6.0-rc.1, 0.5.0-rc.2 |
| Windows, Apple silicon and Intel Mac workers               | 0.8.0-rc.1, 0.7.0-rc.1, 0.6.0-rc.1, 0.5.0-rc.1, 0.4.2-rc.2, 0.4.1-rc.4 |

The sole legacy Linux portable worker (0.1.0-rc.2) remains because no newer Linux
package exists locally. It is not a claim of current desktop feature parity.
Existing local development/tool images and upstream base tags remain available.
The active local containers use older development images; their running images
are protected in addition to the six production release sets.

## Completed cleanup

- Removed 248 obsolete package/cache/worktree entries, approximately **28.86 GiB**
  of local files. This includes superseded coordinator/worker builds, old installer
  copies, disposable packaging intermediates, the Phase 01 verification checkout,
  project npm/pip/uv caches and root lint/test/type caches.
- Removed five clean, fully merged historical Git worktrees using `git worktree
remove`. Their commits are reachable from main.
- Removed **145** obsolete Godfather image references and historical regression
  images without force. Unique Docker images decreased from **80 to 19**; reported
  image storage decreased from **7.392 GB to 2.893 GB**.
- Emptied unused Docker builder cache: **674 entries / 27.19 GB** before cleanup,
  zero afterward. Rebuilding will repopulate this reproducible cache. Docker
  storage reclaimed internally may not immediately shrink Docker Desktop's host
  virtual disk file.
- Verified all **717 retained package files** against their pre-cleanup SHA-256
  hashes. Current and retained predecessor packages are byte-identical.
- Removed six merged remote phase branches and seven merged local branches,
  including the old macOS workflow trigger branch. Both local and remote tips were
  checked as ancestors of main, including the local Phase 09 tip that was ahead
  of its own remote. There were no open pull requests and no outstanding branch
  changes to merge. No history was rewritten.

Post-cleanup the same four local containers remain healthy with the same IDs,
images and start times. All four Docker volumes remain; none was pruned. The
extra unused volume was retained because it may contain recoverable data.
Credentials, production environment drafts, deployment receipts, backups and
current/recent test evidence remain. Source tests introduced in early phases
still exercise current authentication, scheduling and worker compatibility and
were retained. Dependency environments and installed tools remain usable.

## Documentation

The root [README](../../README.md) now covers user installation, sign-in,
Consigliere, model setup, first jobs and Docker hosting. The
[documentation index](../README.md) separates user/operator instructions from
[developer setup](../development.md). Fourteen phase runbooks/verification records
are consolidated in [phase history](../history/phases.md), retaining their original
scope and evidence. Relative links and heading references were migrated.

The [coordinator guide](coordinator-installation.md) documents the actual packaged
setup, status, backup and upgrade commands. Existing immutable release bundles
were not rewritten to contain these new documentation files.

Detailed local before/after inventories, exact removed names, original branch tips,
retained hashes and cleanup logs are under the ignored
`.cache/cleanup-2026-10-22/`. They contain no copied secrets.

## Validation and scope

Executed checks after cleanup:

- Python non-integration regression: **344 passed, 4 skipped, 272 deselected**.
  Two coding sandbox tests and one data sandbox test need explicitly selected
  existing images; one test needs host symlink permission. No integration database
  suite was run for this documentation-only change.
- Dashboard component regression: **37 passed**.
- Repository Prettier check, `git diff --check` and `docker compose config --quiet`
  passed. The Windows npm PowerShell shim was blocked by execution policy; rerunning
  via `npm.cmd` passed without changing that policy.
- All **89 Markdown files** passed local target/heading link validation.
- A content comparison against Git HEAD confirmed that all **14** historical
  records retain their prose, commands and evidence, allowing only heading levels,
  whitespace and migrated link destinations to differ.
- Running container IDs/images remained identical after cleanup; all four are
  healthy. All 717 retained package files match their original SHA-256 hashes.

Documentation/source cleanup does not require rebuilding installers or releasing
a coordinator. No source regression
tests were removed. The owner subsequently included the existing VPS in this cleanup. Contributor
computers remain outside its scope.

## VPS cleanup

The owner explicitly selected **Include the VPS too** after the local cleanup.
The existing coordinator was inspected over the established batch-verified SSH
connection. No deployment, service restart, migration or contributor-host change
was performed. The existing deployment lock excluded concurrent upgrades while
planning and applying cleanup.

The VPS has its own deployment history. Its retained coordinator releases are
**0.8.0-rc.1, 0.7.0-rc.2, 0.6.0-rc.2, 0.6.0-rc.1, 0.5.0-rc.2 and 0.4.2-rc.2**.
The locally built 0.7.0-rc.1 coordinator was never deployed there and therefore
is not counted as a VPS predecessor. Current/previous release symlinks remain
0.8.0-rc.1 and 0.7.0-rc.2.

The same six worker versions in the table above remain available for Windows,
Apple silicon and Intel Mac. Five installer sets remain inside retained
coordinator bundles. The oldest set, **0.4.1-rc.4**, was checksum-verified and
preserved with its original manifest under
`/opt/the-godfather/worker-archives/0.4.1-rc.4/` before removing its obsolete
coordinator bundle. It is an operator archive, not a change to public downloads.

Results:

- Removed **41** obsolete release/upload/probe entries totaling
  **13,248,859,347 bytes** (about 12.34 GiB), including 17 old extracted coordinator
  releases and abandoned versioned upload files.
- Removed **80** obsolete image references without force. Unique Docker images
  decreased from **47 to 15**; reported image storage fell from **4.016 GB to
  1.893 GB**. The builder cache was already empty and remains empty.
- Filesystem available space increased by **15,271,280,640 bytes**, about
  **15.3 GB / 14.22 GiB**, after preserving the archived worker set.
- Verified all **131 retained release files** against their before-cleanup
  SHA-256 hashes, plus all retained release image IDs and archived worker checksums.
- All **five services remained healthy**, with identical container IDs, image
  references, mount definitions and start times. All **five volumes**, private
  environment file hashes/modes, backup file sizes/timestamps and release symlinks
  were unchanged. No database restore, backup deletion or volume pruning occurred.

The current public download manifests and all three installers on both hostnames
were checked after cleanup using normal verified HTTPS; all six streamed installer
SHA-256 checks matched. The home page and anonymous/private-file access boundaries
also passed. These checks created no accounts/jobs and made no inference calls.

Server receipts are under
`/opt/the-godfather/state/deployments/cleanup-20261022/`; local inventory, scripts
and public verification are under `.cache/cleanup-vps-2026-10-22/`. No secret values
were copied into those receipts. All eight GitHub repository-check jobs passed
for the preceding local cleanup commit `b75c062`.
