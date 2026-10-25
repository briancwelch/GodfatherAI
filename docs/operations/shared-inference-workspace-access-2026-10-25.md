# Shared inference workspace permission correction

Owner-authorized implementation, 2026-10-25. After local validation, the owner
separately authorized commit, GitHub push and coordinator deployment. Existing
worker installers are retained. Workspace policy changes still require the
workspace administrator's explicit action in Distributed Jobs.

## Behavior

A ready managed engine uses a generated `shared-<setup id>` model identifier.
Allowing its installed Ollama model, such as `qwen3:8b`, does not allow that
separate identifier. Previously, the shared-inference options endpoint silently
omitted the entire group when checking the workspace model allowlist. Both
workers could show Ready while Distributed Jobs returned `{"groups": []}`.

Distributed Jobs now lists an otherwise authorized group with **Workspace
permission required**. Select the group and choose **Allow in this workspace**
as the workspace owner or administrator. This adds only the selected shared model
identifier, then refreshes actual readiness. Submit the job separately after it
becomes Ready. A new/recreated setup needs its own explicit approval.

Members see instructions to contact a workspace administrator. Missing model
discovery, stale availability and pending requests disable the approval action.
The action shows pending, confirmed success and failure feedback. Workspace,
mode and group selections are held while a request is pending.

## Boundaries

- Discovery retains node-owner sharing policy, workspace membership, physical
  worker identity checks and exclusive active-group restrictions. It omits only
  the model-selection permission check so the missing model grant can be shown.
- The authenticated, same-origin POST derives the exact model identifier from
  the authorized group and matching leader deployment. It requires workspace
  administration; platform administration alone does not grant that permission.
- A workspace lock serializes additive grants. Existing model/tool permissions
  remain intact; duplicate requests do not duplicate the identifier or audit.
- Submission, scheduling and report validation still enforce the full model
  allowlist, member consent, health, credentials, leases and fencing.
- No existing workspace policy is changed automatically. No migration, worker
  build, model download, paid API call or physical inference is needed.

## Validation

- **39 PostgreSQL integration tests passed** across shared inference and managed
  setup. Regressions cover empty/restricted allowlists, actual generated aliases,
  active-group reservations, additive/idempotent audited grants, successful
  scheduling after approval, later revocation, missing/mismatched deployments,
  the model-count limit, workspace roles, private workspaces and node-owner denial.
- **479 Python unit tests passed, 5 optional environment tests skipped.** Skips
  concern existing pinned sandbox images, POSIX mode and Windows symlink support.
- **68 dashboard component/polling tests passed**, including administrator/member
  controls, stale/pending/missing-model states and the exact POST bridge boundary.
- Python lint/format and strict typing passed. A fresh type-check cache was used
  after an incremental import-cache error; both Windows and the freshly built
  Linux API image passed strict typing across all 204 source files.
- Dashboard lint, strict TypeScript, formatting and the optimized Next.js build
  passed. The API development/test image built successfully.

Database checks used the isolated Compose project
`godfather-shared-access-check`, with no host database port and only its disposable
`godfather_test` database reset by the fixture. Existing development/production
databases, artifacts, credentials, account keys and workspace policies were not
changed. No schema migration or installer build was needed.

Real signed-in local browser flows, production deployment/acceptance and physical
multi-computer inference were not performed. Approval adds a permission; it does
not submit a job, prove GPU performance or authorize paid inference.

## Changed files

- `apps/api/src/godfather_api/shared_inference.py`: visible permission state and
  additive, administrator-authorized shared-model grants.
- `apps/dashboard/src/components/shared-inference-jobs.tsx`: scoped approval,
  actual availability refresh and permission/pending/result feedback.
- `apps/dashboard/src/lib/control-server.ts`: allowlisted approval POST.
- `tests/integration/test_shared_inference.py` and
  `tests/integration/test_shared_engine_setup.py`: persistence, execution and
  authorization regression coverage.
- `tests/dashboard-components.cjs`: permission UI and bridge regressions.
- `docs/decisions/0025-shared-inference-and-task-variables.md` and this report:
  updated decision and operation/validation evidence.
