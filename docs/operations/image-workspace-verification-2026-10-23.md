# Image workspace permission usability verification, 2026-10-23

The owner authorized the fix and deployment. Scope is the coordinator and website;
Consigliere 0.9.0-rc.2 remains compatible and its installers are preserved.

## Problem and behavior

An empty workspace model allowlist hid all cloud image models even though the
owner's API connection and computer were ready. The page then incorrectly
reported a missing local image model. The blocker was workspace permission.

The options API now separates permitted and workspace-restricted cloud inventory
while preserving node-owner and private account-key checks. Images displays the
restricted choices and the exact workspace restriction. Owners/administrators can
choose **Allow selected model in workspace** using the existing model-access
endpoint. Members receive administrator guidance. Prompt and selection survive
the permission update; a failed update leaves a visible error and does not enable
generation. The sidebar stops suggesting worker/key setup for this blocker.

The form visibly defaults to an available local provider or an already configured
cloud provider. Users still select an exact model/computer. Manual provider choice
survives refresh. **Generate image** requires an online permitted selection, prompt,
provider billing/data-egress consent and worker-processing consent. Allowing a
model never generates an image. No workspace grant is changed by deployment.

## Validation

- Windows Python unit suite: **379 passed, 4 skipped**. Skips require explicitly
  configured local sandbox images or host symlink permission.
- Complete PostgreSQL integration suite: **282 passed**. The added cases cover
  both providers, empty workspace allowlists, explicit grants, unassignable
  restricted jobs, member denial and private-key inventory isolation.
- Dashboard components: **43 passed**. Ruff formatting/lint, strict mypy (183
  source files), TypeScript, ESLint, Prettier and optimized dashboard build passed.
- Edge browser acceptance passed for restricted inventory, exact blocker,
  rejected and successful explicit grants, retained prompt/selection, member
  guidance, both required consents, no automatic generation, provider-specific
  messages and a manual local choice surviving refresh. Desktop/light and
  mobile/dark layouts had no overflow or browser page errors.

No real provider key was read and no billable generation was performed by these
checks. PostgreSQL tests used the disposable `godfather_test` database. Browser
tests used synthetic model inventory and account references with the actual
optimized dashboard. Physical provider/account generation remains unverified.

Deployment results will be recorded after packaging and production verification.
