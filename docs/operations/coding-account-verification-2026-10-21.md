# Coding/account usability verification — 2026-10-21

Candidate **0.3.1-rc.3** adds account API key entry, project setup, responsive native
windows, default tray restore and corrected download layout. The owner explicitly
approved activation, and it was deployed on 2026-10-21. A subsequent same-computer
reconnection repair is tracked in the [reconnection report](worker-reconnection-2026-10-21.md).

The [user/operator guide](coding-and-account-setup.md) and
[decision record](../decisions/0017-account-connections-and-coding-project-setup.md)
describe the scope. The owner explicitly chose encrypted account storage and
provider-managed billing, then requested fresh worker builds and tray/resize fixes.

## Implementation

- Account settings replaces the old billing-management UI. Choose OpenAI or
  Anthropic, paste a key and select owned computers. Connection testing lists
  models. Computer permissions can change without key re-entry. Google login
  remains independent. No Godfather pricing or budget setup is required.
- Migration `0010_account_provider_keys` adds encrypted account key records and
  optional references on existing provider connections. Existing local provider
  credentials/history remain intact. AES-GCM binds ciphertext to owner/provider;
  its separately configured server key never belongs in a release or database.
- Delivery requires explicit computer selection, matching node/owner/session,
  live individual credentials and worker opt-in. Workers retain keys only in
  memory. Account responses, scheduler state, artifacts and logs exclude secrets.
- Coding projects selects folder, workspace, installed local Linux image, file
  scope and test command. Resume supplies the existing coding/workflow flags and
  advertises the configured repository. Only the connected owner is granted use.
- Worker windows wrap and scroll within maximum dimensions; tray activation
  restores the window. The download panel has separate spaced items, wrapping
  checksums and a responsive address/copy row.

## Executed checks

Counts overlap; separate runs are not additive.

| Check                                                                            | Result                                                                                                                                                                                                          |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full isolated PostgreSQL/API/Python suite before final permission/UI refinements | 444 passed, 3 optional native Git/container checks skipped                                                                                                                                                      |
| Final targeted account/legacy provider PostgreSQL tests                          | 13 passed; includes owner isolation, node opt-in, explicit grants, encryption binding, permission changes without key re-entry, disconnect, missing vault key and provider billing without prices/budgets       |
| Native Windows non-integration suite                                             | 250 passed, 2 optional pinned-container tests skipped                                                                                                                                                           |
| Ruff and strict mypy                                                             | Passed; 132 source files checked by mypy                                                                                                                                                                        |
| Dashboard lint, TypeScript, component tests and production build                 | Passed; 15 component tests                                                                                                                                                                                      |
| Native Windows Tk/tray lifecycle                                                 | Fresh/saved identity, tray default restore, resize, scoped project add/remove, pause/resume and quit passed using synthetic controller/identity; no actual enrollment or inference                              |
| Edge local fixture browser checks                                                | Desktop/narrow-screen downloads, expanded checksums without item overflow, nonoverlapping buttons/text, account key entry, explicit computer selection, password field clearing and no JavaScript errors passed |
| Final coding/helper checks with an existing local Linux test image               | 22 passed, including real Git ownership regression, scoped snapshots, isolated tests and reviewable synthetic-model patch                                                                                       |
| Final saved coordinator package                                                  | Passed image/config checks, fresh/repeat migration, private service health, anonymous denial, database/artifact restore and restart persistence                                                                 |
| Final source cross-platform CI                                                   | [All jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/39665218160), including Python/dashboard matrices and Linux PostgreSQL, scheduler, worker and recovery checks                         |

Private local evidence is under `.cache/coding-setup/`. The browser used a loopback
fixture API and fresh browser context; it did not forge a production session or
access a real user's account. No provider key was supplied and no real billable
inference, model download or normal-user host installation was performed.

## Built candidates and remaining acceptance

All packages below contain source revision
`1a68aa01b4940632613c027ad1003a1dc8dbdaaf` with clean source. Subsequent
verification-document commits do not change those binaries.

| Package                                                 | SHA-256                                                            |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `godfather-0.3.1-rc.3-linux-amd64.tar.gz`               | `01ceb16be5767731f71e1d5eefad10013bf81173e106660087d2e88fc056dce1` |
| `godfather-worker-0.3.1-rc.3-windows-x64-setup.exe`     | `d2e44e27f08ad0a14cc23572c2e461b0b8f8684f9834a0e600d5b94697f596aa` |
| `godfather-worker-0.3.1-rc.3-macos-arm64-installer.dmg` | `763378b29c4f7de4ae7059a405dc73eacc6c54f16c08a12d5fcc7f71ecda5fec` |
| `godfather-worker-0.3.1-rc.3-macos-x64-installer.dmg`   | `a4db8a4b10b3b0cc38b72978ac90246261f659bdc00bc67a378baa3e796ecea2` |

The Windows frozen installer passed temporary installation/reinstallation,
packaged Tk/tray and isolated Windows Credential Manager checks. Both native Mac
builds and their packaging checks [passed on GitHub runners](https://github.com/briancwelch/GodfatherAI/actions/runs/39665260295).
Installer hashes were verified before inclusion in the coordinator package.
The PostgreSQL image matches the previous release. Coordinator package evidence
is `.cache/release-tests/a2fe2c341a25/result.json`; its HTTP tests used loopback,
not public TLS, Google sign-in or SSH deployment.

Windows remains unsigned and Mac distribution remains ad-hoc signed without
Developer ID/notarization. Physical recipient interaction, real account key entry
and a live coding task are separate checks. Native dispatch tests do not prove
physical double-click behavior on every Mac desktop.

Activation requires the new migration and a separately generated private vault
key, retained across upgrades/restores. Encryption at rest does not protect against
compromise of the trusted API process and its private configuration.

At the user's explicit request, the old local worker process (PID 10792, the
`0.2.0-rc.4` Windows CLI) was stopped. A subsequent process inventory found no
local Godfather workers running. Saved settings and credentials were preserved;
no replacement was started, enrolled or installed into the user's normal app
directory. Real account-key/coding acceptance remains pending. No later workload
phase was started.

## Authorized production activation

The backup-based installer deployed `0.3.1-rc.3` from the exact package above.
Schema `0010_account_provider_keys` applied; all five services were healthy. The
separate vault key was generated privately on the host, existing environment
values and proxy token were preserved, and the environment remained root-owned
mode 600. PostgreSQL and Redis still had no published host ports.

Stable record fingerprints matched before/after: 2 users, 2 Google identities,
2 workspaces, 2 credentials, 1 node ownership/policy, 3 jobs, 2 artifacts,
1 checkpoint and 1 existing provider connection. No account provider keys were
seeded. The node was offline as expected after the requested local stop.
The paired backup at
`/opt/the-godfather/state/backups/20261021T200919-643668` passed checksum,
`pg_restore --list` and artifact archive checks. Private evidence is
`.cache/coding-setup/postflight-deploy.log`. Fresh signed-in account/coding
acceptance remains pending; public checks for the subsequent repair are recorded
in its report.
