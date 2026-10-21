# Consigliere and UI release verification — 2026-10-21

Owner-authorized usability update, committed and pushed to GitHub, built and
activated on the existing VPS. **Command Center 0.3.3-rc.3** serves the verified
**Consigliere 0.3.3-rc.2** Windows, Apple Silicon and Intel Mac installers under
**Nodes → Downloads**. See the [UI and upgrade guide](consigliere-ui.md).

## Implemented scope and files

- Dashboard: `command-center.tsx`, `administration.tsx`, `operational.tsx`,
  `application-shell.tsx`, `command-icon.tsx`, connection/pairing components,
  contracts, bridge allowlist, icon data and CSS. Job submission/information open
  by default; job diagnostics, node downloads and administration use tabs.
  Jobs, nodes, events, checkpoints and administration lists use 25-item AJAX pages.
  Member/account selection is paged/searchable. Explorer/ribbon icons are distinct,
  and dark surfaces are neutral black/grey.
- API: `administration.py` and `command_center.py` add bounded, authorized counted
  pages and a separate checkpoint route. Legacy administration arrays remain
  compatible. No schema migration, lease, permission or model-routing change.
- Desktop: worker `desktop_app.py`, layout, native icon assets, Windows setup,
  `app_installation.py`, `macos_setup.py` and `tailscale.py`; native build/check
  scripts and the existing Mac workflow. Consigliere uses The Godfather AI
  branding, a grouped command ribbon and a stable replacement install location.
  Old recognized app versions are removed while saved identities/settings and
  existing startup consent are retained. Running workers block replacement.
- Release: Caddy download allowlist and `check_release.py` now verify actual
  installer retrieval and hashes through both hostnames. Tests and user/design
  documentation accompany the changes.

Tailscale discovery is read-only and optional. An installed, connected client is
detected, including on this Windows computer during verification. Existing private
routes/DNS are used where configured; connecting to a tailnet alone does not prove
private coordinator reachability. No Tailscale installation, login, routing, DNS,
ACL or host permission change was made.

## Executed verification

- Disposable PostgreSQL/API suite in source CI: **497 passed, 2 optional pinned
  container checks skipped**. Pagination tests cover disjoint ordered pages,
  counts, search, invalid offsets, cross-user denial and worker/anonymous denial.
  Final focused PostgreSQL changes were also checked locally (63 checks, followed
  by the final 3 pagination scenarios).
- [Complete source CI for the UI/worker source](https://github.com/briancwelch/GodfatherAI/actions/runs/39685786946)
  passed: Python 3.12/3.14, Windows/macOS/Linux Python/dashboard checks, npm audit,
  real migrations, process health, restart/outage recovery, 100 jobs without
  conflicting assignments, inference and interrupted workflow recovery.
  Ruff formatting/lint, strict mypy (including Linux/Mac platform modes), frontend
  formatting/lint/types, 19 component tests and production builds passed.
- Fresh Edge fixtures at 1440px and 390px passed default expansion, 25-row AJAX
  pages without document navigation, filter resets, tab/keyboard behavior,
  checkpoint pages, independent administration positions, account search/paging,
  Explorer/ribbon icons, neutral dark surfaces and no JavaScript errors.
  Evidence: `.cache/consigliere/browser-result.json` and screenshots.
- Windows packaged temporary install/reinstall, bundled Tk/tray startup and an
  isolated Credential Manager entry passed. Source tray/window smoke covered
  pause/resume, restore, resize, scoped projects and quitting. Upgrade tests cover
  old-version cleanup, settings preservation, rollback after a failed swap,
  running-app refusal, unknown-folder refusal and startup consent.
- [Both native Mac builds](https://github.com/briancwelch/GodfatherAI/actions/runs/39685829646)
  passed lifecycle, packaging, architecture/library/signature checks and DMG
  startup checks. Mac replacement behavior is covered by filesystem tests.
- The final saved-image release check passed production config, migrations,
  private service health, anonymous denial, persistence/restart and paired
  database/artifact restore. **All three installers were actually downloaded and
  hashed through both proxy hostnames**. Evidence:
  `.cache/release-tests/f835a89f594a/result.json` and
  `.cache/consigliere-rc3/release-check.log`.

The initial live rc.2 check caught a missed old-name-only Caddy download allowlist.
The correction is coordinator-only; the already verified worker binaries remain
unchanged. The new package test covers this failure directly. The proxy correction
also passed 14 focused packaging tests, strict typing and all native source and
dashboard CI matrices; its [follow-up CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39687917266)
records the repeated container acceptance run, which was still running when this
report was written. The complete base run above passed all container gates; the
final proxy change passed the additional saved-package and live download checks.

## Immutable artifacts

Worker source: `10480db727a58560ff488af021316466afa50616`.
Coordinator source: `07bcc6e3bfab9d1ad1dfe20326b8c396d3ffb69d` (only the proxy
allowlist and release-check correction follow the worker source). Both were clean,
committed builds; manifests record provenance.

| Artifact                                           | SHA-256                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `consigliere-0.3.3-rc.2-windows-x64-setup.exe`     | `3c90922d3a0cf24b3f4a34f6b4bc76047131ad01519694704733d822c4f6755c` |
| `consigliere-0.3.3-rc.2-macos-arm64-installer.dmg` | `c0b024828dc312f057d590dc68e2cb3d35b54c026cf835dbec9b0a73a90202ac` |
| `consigliere-0.3.3-rc.2-macos-x64-installer.dmg`   | `206e62ba4b5b5388d8fc5f1ed08aa8e91793702872d7b3452a0943e372077134` |
| `godfather-0.3.3-rc.3-linux-amd64.tar.gz`          | `43f99ca483c7bc16078e8e0411d645cb8c300b45026ebc291d6c84e8d63aac77` |

## Production activation and limits

The existing `root@137.184.227.74:/opt/the-godfather` deployment reports rc.3
and the exact coordinator source above. All five services are healthy. PostgreSQL
and Redis have no published host ports; schema remains
`0011_worker_reconnection`. The environment, including vault/proxy keys, stayed
byte-identical and mode 600. No DNS, cloud account or firewall configuration was
changed. SSH used the established PuTTY/Pageant authentication.

Before/after fingerprints matched for 2 users, 2 Google identities, 2 workspaces,
3 credentials, 1 node ownership/policy, 8 jobs, 4 artifacts, 2 checkpoints,
2 provider connections and 1 encrypted account-provider key. The existing node
identity remains present; it was offline at final inspection, with no active jobs.
No real user worker was automatically installed or started.

The final paired backup is
`/opt/the-godfather/state/backups/20261021T224237-717994`; its checksums, PostgreSQL
dump listing and artifact gzip validated. The earlier rc.2 backup was retained.
Actual production restore was not performed; restore execution used the disposable
release environment. Preservation/upgrade evidence is in
`.cache/consigliere-rc3/upgrade.log` and `postflight.log`.

Public TLS checks fetched all three installer files with HTTP 200 and verified
their hashes; the served manifest matches the staged one. Anonymous account,
checkpoint, result-action and worker access remains denied; foreign-origin writes
and private file/API paths remain blocked. A fresh browser verified login,
pairing sign-in requirements and the real Google redirect with PKCE and
identity-only scopes, without signing into a private account. Ordinary DNS/TLS
also returned HTTP 200 at `137.184.227.74`. Evidence:
`.cache/consigliere-rc3/public-result.json` and `live-browser-result.json`.

Existing unsigned Windows/ad-hoc signed Mac status remains. No Developer ID,
notarization, physical recipient installation, real paid inference or live human
session acceptance is claimed. Next acceptance is for each owner to quit their old
tray worker, install Consigliere from Downloads, and use their retained connection
and explicitly permitted project. No later workload phase was started.
