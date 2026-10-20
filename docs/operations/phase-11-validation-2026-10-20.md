# Phase 11 local validation - 2026-10-20

Scope: the explicitly authorized coding/frontier/results assignment. Google login,
node identity and provider API credentials remain independent. No real frontier
key was supplied, no paid inference was performed and no production data was used.

## Implemented

- Independent owner/node-bound provider connections, private/approval/limited
  policies, revocation, scoped grants, integer micro-USD reservations and usage.
  Secrets remain in worker-local OS stores; the coordinator has no key-upload API.
- Native OpenAI Responses and Anthropic Messages adapters with bounded streaming,
  structured-output/tool-call contracts, safe errors and provider token usage.
  Unsupported cache-pricing categories retain accounting liabilities for review.
- A single coding step in the existing runtime: approved committed Git snapshots,
  literal code search, validated file edits, actual Git diffs and owner-approved
  tests/build commands in a restricted local Linux container. Original repositories
  are preserved; interrupted commands require review and late writes are fenced.
- Answer-first results, safe Markdown, highlighted code/diffs, readable JSON,
  tables/charts and supported document/media envelopes, copy/download controls,
  partial/error states and expandable technical history. No new image/report
  generation subsystem or arbitrary remote media loading is implied.
- Provider Connections, agent connection/model selection, explicit paid-run
  consent, local-only ordered fallback, provider activity/audit integration and
  runtime release metadata in the status bar.
- Additive migration `0009_provider_connections`. Existing identity, job, worker
  ownership and production volumes are not replaced by this migration.

## Executed checks

| Validation                                                         | Actual result                                                                                                    |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Full PostgreSQL-enabled suite, disposable `godfather_test`         | 403 passed, 3 skipped                                                                                            |
| Full native Windows suite with actual Git/container checks enabled | 224 passed, 182 database-only skips                                                                              |
| Frontend component tests                                           | 12 passed                                                                                                        |
| Ruff formatting/lint and strict mypy                               | Passed                                                                                                           |
| Dashboard formatting, ESLint, TypeScript and production build      | Passed                                                                                                           |
| Native container coding fixture                                    | Real Git diff and actual passing test; original preserved                                                        |
| Sandbox boundary probe                                             | Host secret environment absent, host snapshot read-only, no external route, test writes disposable               |
| Credential store contract mocks                                    | Windows/macOS/Linux namespaces and fail-closed unavailable store verified                                        |
| Authenticated browser/worker acceptance                            | Real PostgreSQL, native Windows worker, installed `qwen3:8b`, actual Git/container tests and persisted artifacts |

The three skips in the coordinator test image are deliberate: it contains no Git
or Docker daemon access. Those worker-side tests were separately executed on the
native Windows host. Counts describe separate runs, not disjoint tests to add up.

GitHub CI additionally exposed two pre-existing references to the optional Windows
`CREATE_NO_WINDOW` constant in worker discovery/health tooling. They now detect the
actual subprocess feature with a zero fallback. Strict mypy was rerun successfully
for `linux`, `darwin` and `win32` targets before rebuilding the final candidate.

The browser harness mocks **Google HTTP responses only**, using actual Authlib
verification, sessions, invitations and RBAC. It verifies private connection
visibility, workspace artifact denial, real job/result persistence, agent management,
worker revocation, logout and existing node-owner restrictions. It does not establish
real Google account acceptance after a production upgrade. Screenshots and detailed
test logs remain in ignored `.cache/phase11` and `.cache/phase09-runs` directories.

## Release and remaining acceptance

The clean source is packaged using the established source-free Linux AMD64 release
process and standalone Windows-worker builder. Generated manifests record the exact
release, source revision, image IDs, build time and migration head. The release smoke
checker compares image metadata and verifies fresh/repeat migrations, private proxy
behavior, backups/restores and durable volumes in a separately owned local project.
Packaging and its generated evidence occur after this source commit; consult those
manifests/results for the exact artifact identity rather than hardcoding it here.

Automatic approval review rejected even the read-only SSH inspection of the existing
production Droplet, stating that authorization for that specific private host was not
explicit in its trusted transcript. No workaround or indirect connection was used.
Deployment, live version/results/authentication checks and production coding acceptance
therefore remain pending exact host-access approval.

Real OpenAI/Anthropic acceptance requires owner-local API credentials plus explicit
authorization for billable calls. OS credential-store behavior was mocked, not tested
against actual provider keys. Physical macOS/Linux workers, new native macOS builds,
and real provider rate/cancellation/billing behavior remain unverified. Paid retries,
paid fallback, server-side API-key storage and unrestricted coding tools stay disabled.

The current task remains Phase 11 until its pending live gates are resolved; no
later phase, DNS/Google Cloud change or new infrastructure is authorized here.
