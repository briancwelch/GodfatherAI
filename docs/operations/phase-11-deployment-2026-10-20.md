# Phase 11 deployment verification - 2026-10-20

The user explicitly approved SSH access to the existing production host and
deployment of the reviewed candidate. The established source-free installer
upgraded `0.1.0-rc.7` to **`0.2.0-rc.4`**, source revision
`538df376740632faf806d8bb6a832c2cd7cdb5ef`. The separate documentation commit
recording this result is not the deployed application revision.

## Executed production checks

- The transferred archive matched trusted local SHA-256
  `a03ab4fc92f51562d79507de4ad22e3daccdfe136175cb974ea54304a328a85d`;
  packaged-file checksums and production configuration validation passed.
- Proxy routing and Compose configuration matched the previous release. No DNS,
  Google Cloud configuration, production credential or host policy was changed.
- The installer took a quiesced, paired database/artifact backup before migration.
  Backup checksums, `pg_restore --list` and compressed artifact integrity passed.
  The existing PostgreSQL image and persistent volumes were retained.
- Migration advanced from `0007_founder_bootstrap` to
  `0009_provider_connections`. API, dashboard, proxy, PostgreSQL and Redis became
  healthy; current/previous links identify the new and old release respectively.
- Before/after user, node-owner and worker-credential fingerprints matched.
  Existing user/node/workspace/job/credential counts matched. The production
  environment file checksum and private permissions were preserved.
- The existing Windows worker reconnected and returned online. Existing
  authenticated browser requests continued succeeding after the upgrade.
- Real HTTPS returned 200 with normal certificate validation. The direct public
  API health path returned 404 and public worker registration returned 403.
- Headless browser acceptance verified the live login shell, anonymous dashboard
  and provider-connection API denial, real Google authorization redirect, exact
  callback, `openid email profile` scopes and PKCE S256, with no page errors.
- Runtime metadata reports `0.2.0-rc.4`, the exact revision above, build time
  `2026-10-20T23:39:12.681703+00:00` and environment `production`. The user
  refreshed their signed-in Command Center and confirmed the footer version and
  existing job results. This was user-assisted authenticated UI acceptance.

Private deployment logs, backup location and machine-specific fingerprints remain
in ignored operator evidence under `.cache/phase11-deployment`; production data
and secrets are not included in this document or Git.

## Remaining acceptance

The packaged Windows worker completed real local Ollama/Git/container coding
acceptance before deployment. A coding task through the live coordinator has not
been executed: it needs the updated worker and owner-approved repository/model/
command configuration. The existing worker was left operational without replacing
its installation or changing owner contribution permissions.

No provider connection or key was added in production, and no paid API call was
performed. Real OpenAI/Anthropic acceptance needs owner-local credentials and
explicit spending authorization. Physical macOS/Linux inference and a fresh
automated Google account sign-in were not tested. The computer-use launcher failed;
the public browser checks used the existing Playwright fallback, while signed-in
version/results were confirmed directly by the user.

GitHub checks passed for the deployed application revision, including Python and
dashboard matrices on Windows/macOS/Linux, PostgreSQL tests and historical
process/recovery probes. See [local validation](phase-11-validation-2026-10-20.md).
No later milestone was started.
