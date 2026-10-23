# Project cleanup - October 22, 2026

Owner-authorized maintenance of the local project and GitHub branches. No new
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
tests were removed. The existing VPS and contributor computers are outside this
local cleanup unless separately included by the owner.
