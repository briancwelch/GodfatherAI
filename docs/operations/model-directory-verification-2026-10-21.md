# Local and account model selection correction

Owner-authorized correction begun 2026-10-21 (Pacific), deployed 2026-10-22.
The full correction and rebuilt workers are **0.4.1-rc.4**. Final coordinator
**0.4.1-rc.5 is deployed**, retaining those verified workers and including the
dashboard search guard. Activation and preservation checks passed.

## Actual cause

Read-only production diagnosis found Carbon advertising installed `qwen3:8b`
and 36 OpenAI models. Test Workspace had `allowed_models=[]`, so its model list
and agent options were empty despite that real inventory. The download catalog
did not carry installed-model metadata, so it offered an installed model and
then displayed the API's duplicate-install refusal. The default desktop model
configuration also omitted the workflow protocol required by model-only agents.
No plaintext API key was read, decrypted, logged or changed during diagnosis.

## Behavior

- Models and **Add / use model → Local & API models** show discovered local/API
  inventory, node names, workspace access and worker availability independently.
  An offline worker's recorded inventory remains visible and is labeled offline.
- **Allow in workspace / create agent** adds only the selected discovered model
  under workspace-owner/admin authorization, then opens the agent editor with
  that exact local or provider-connection model selected. Existing allowlists and
  tool restrictions remain intact; execution is never silently enabled globally.
- **Download local model** labels existing node/runtime/model tuples **Already
  installed**, disables those radio options and offers **Use installed model**.
  A concurrent installation response refreshes inventory and returns to selection.
- Basic local/account-model workers enable existing model-only workflows without
  granting filesystem, shell or other host tools. Coding/data opt-ins remain
  separate. Updated desktop workers are required for this execution correction.
- API selections still require explicit paid/provider consent on definitions and
  runs. The key remains private; selecting a model never sends an inference call.

## Focused validation

Authenticated PostgreSQL regressions cover a newly created empty-allowlist
workspace discovering local/OpenAI inventory, safe installed metadata, explicit
single-model enablement, idempotency, exact selected agent creation, per-run paid
consent, actual scheduler assignment of that deployment, member/platform-admin
denial, unadvertised models, worker credential denial and key-disconnect withdrawal.
All provider catalog HTTP is mocked; no real or billable inference was executed.

Browser acceptance against the production dashboard build and isolated fixtures
passed local/API visibility, disabled installed downloads, use without downloading,
workspace enablement, automatic editor opening with the correct local/API model,
API consent, mobile dialog layout and absence of JavaScript errors. Desktop/mobile
screenshots were visually inspected. Evidence is under `.cache/model-download-fix/`.

See [ADR 0021](../decisions/0021-discovered-models-and-workspace-use.md) and
[the model setup guide](consigliere-ui.md#add-a-local-model).

## Build and validation evidence

The full correction source is `5ee69e69cdca90a62403bf9da3c14f630655fa3d`.
The final coordinator source is `d10edf42d59732ccf97ace579aa2d950602957b7`, whose
only application delta is preventing Enter in the model search field from
submitting the download form. Both application commits were pushed before building.

- Full disposable PostgreSQL-backed suite: **530 passed, 3 optional skips** for
  unselected existing coding/data sandbox images.
- New authenticated regression tests: local and account API models can proceed
  through discovery, explicit workspace authorization, agent creation and exact
  scheduler assignment; paid jobs without run consent are rejected. No model
  inference is executed by those tests.
- Dashboard **22 component tests**, ESLint, strict TypeScript, production build,
  Prettier, Python Ruff and mypy (**157 files**) passed.
- Native Windows installer temporary install/reinstall, bundled Tk/tray startup
  and isolated synthetic OS-credential checks passed. Desktop lifecycle smoke
  passed for fresh/saved fixture identities.
- [Mac native builds](https://github.com/briancwelch/GodfatherAI/actions/runs/39737091012):
  both Apple Silicon and Intel jobs passed, including unit tests, native desktop
  lifecycle, DMG creation, architecture/framework checks and packaged startup.
- [Full model-fix CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39737091849):
  **all eight jobs passed before 0.4.1-rc.4 activation**, including Windows/Mac/Linux
  Python/dashboard checks, real PostgreSQL migrations, restart/outage recovery,
  four-worker health, 100-job scheduling, inference and checkpoint resumption.
- [Final guard rerun](https://github.com/briancwelch/GodfatherAI/actions/runs/39739258169):
  GitHub refused to start all eight jobs, reporting failed account payments or a
  spending-limit restriction. Those jobs did not execute. No GitHub billing setting
  was changed. The final one-line guard passed local browser acceptance (including
  Enter in search), lint/type checks, 22 component tests and production build.
  See `.cache/model-directory-rc5/ci-blocker.txt`.
- Both immutable saved-image releases passed isolated validation, including exact
  metadata/images, production config/Caddy/shell checks, migrations, private
  services, anonymous denial, all worker downloads through both proxy hostnames,
  real paired database/artifact restore and restart persistence. Evidence:
  `.cache/release-tests/cb8948acc450/result.json` (rc.4) and
  `.cache/release-tests/c5bea7f37395/result.json` (rc.5).
- Browser acceptance also covered installed-model duplicate/race recovery, exact
  local/API selection, automatic editor opening, API consent, desktop/mobile
  layout and absence of JavaScript errors. Screenshots were visually inspected.
  Fixture APIs/OIDC/provider catalogs are not private-account or billable-inference
  acceptance.

## Immutable artifacts

Final coordinator archive: `dist/godfather-0.4.1-rc.5-linux-amd64.tar.gz`.
SHA-256: `87d7363d32fcf6db1b224861fc446de76292071fd5103240ffbe49300e3cf270`.
Build metadata: `2026-10-22T07:15:33.861162+00:00` (UTC).
Schema remains `0013_command_center_deletion`; no migration was added.

| Worker installer                                   | SHA-256                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `consigliere-0.4.1-rc.4-windows-x64-setup.exe`     | `afc574522c8f22f0407e6fe1ff366031ffabcc56ad355f9d2cdd40850c1f93aa` |
| `consigliere-0.4.1-rc.4-macos-arm64-installer.dmg` | `e81f3f145b20bb5660ffdd2efbb1a48d3c74d315142a987d617311db7c87280e` |
| `consigliere-0.4.1-rc.4-macos-x64-installer.dmg`   | `b3a477dfef26ce271472b8ce5b56464df6ff72ffafeea574cc66fa9de6ca1b98` |

The initial rc.4 coordinator archive hash is
`0cbb8445d7b3a1a777d569c487af74a24122158390bec55be9f963216ab6d69b`.
The final coordinator includes the exact same verified worker bytes.

## Live checks and limits

The rc.4 postflight verified all five services healthy and unchanged production
environment bytes/mode 600, including vault/proxy keys. Record fingerprints
matched for 2 users, 2 Google identities, 3 workspaces, 4 credentials, 2 node
ownership/policy records, 8 jobs, 3 agents, 4 artifacts, 2 checkpoints, 2 provider
connections and 1 encrypted account key. Memberships remain empty.
Its validated paired backup is
`/opt/the-godfather/state/backups/20261022T070949-940544`.

Read-only live catalog checks confirmed **1 Ollama and 36 OpenAI models** for
Test Workspace's identity-authorized inventory. Its empty model allowlist was
preserved; users explicitly authorize a selected model through the new action.
Carbon was offline and advertised workflow protocol 1; Radium was online with
no model-workflow opt-in. Inventory visibility is distinct from readiness to run.
No account key was decrypted, workspace policy changed, job submitted or paid
inference called as a live fixture. See `.cache/model-directory-rc4/catalog-check.log`.

All three rc.4 installers returned HTTP 200 with verified hashes on both public
hostnames. Anonymous/private endpoints and foreign-origin mutations, including
the new model-access endpoint, remained denied. Evidence is under
`.cache/model-directory-rc4/` and final checks under `.cache/model-directory-rc5/`.

Existing installed workers were not silently replaced or reconfigured. Install
Consigliere 0.4.1-rc.4 for basic model-only workflow execution; existing project/
workload-enabled workers retain compatibility. Keys, computer grants, consent
settings and project permissions are preserved. Windows remains unsigned; Macs
remain ad-hoc signed. Physical recipient and real paid-provider acceptance remain
unclaimed. Phase 13 has not begun.

Final rc.5 postflight verified `/opt/the-godfather/state/current` points to
`releases/godfather-0.4.1-rc.5-linux-amd64`, exact source/build metadata, all five
healthy services, private database ports, the same complete preserved record
fingerprints and byte-identical mode-600 production environment. Its paired backup
`/opt/the-godfather/state/backups/20261022T072344-948549` passed checksums, dump listing
and artifact gzip integrity. Production restore was not performed. The final live
catalog again contained 1 local and 36 OpenAI models; Carbon remained offline.
Final public verification passed **43 HTTP checks** and **six installer hash
checks** (Windows/Apple Silicon/Intel on both hostnames), with normal DNS/TLS and
continued anonymous/foreign-origin denial. No live inference or model pull ran.
