# Local and account model selection correction

Owner-authorized correction, build and deployment, 2026-10-21 (Pacific).
Candidate coordinator and workers: **0.4.1-rc.4**. Activation evidence follows
after release verification; this initial section records the implementation.

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
