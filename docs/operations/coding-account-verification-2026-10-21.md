# Coding/account usability verification — 2026-10-21

Candidate **0.3.1-rc.1** adds account API key entry, project setup, responsive native
windows, default tray restore and corrected download layout. It is not deployed
by committing this report. Production remains on `0.3.0-rc.4` until activation.

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

Private local evidence is under `.cache/coding-setup/`. The browser used a loopback
fixture API and fresh browser context; it did not forge a production session or
access a real user's account. No provider key was supplied and no real billable
inference, model download, host installation or production change was performed.

## Native candidates and remaining acceptance

Fresh Windows and native ARM64/Intel Mac candidate builds are pending at this
source checkpoint; record their actual results and hashes after completion.
Windows remains unsigned and Mac distribution remains ad-hoc signed without
Developer ID/notarization. Physical recipient interaction, real account key entry
and a live coding task are separate checks. Native dispatch tests do not prove
physical double-click behavior on every Mac desktop.

Activation requires the new migration and a separately generated private vault
key, retained across upgrades/restores. Encryption at rest does not protect against
compromise of the trusted API process and its private configuration. Existing
worker processes were not replaced or stopped. No later workload phase was started.
