# GitHub main synchronization - 2026-10-20

## Scope and history

Synchronize the approved local development repository to
`https://github.com/briancwelch/GodfatherAI.git`, preserving both histories without
force pushing, deployment, releases, tags, or repository settings/secrets changes.

The starting branch was `phase-09-google-oidc` at
`1fd7ace` and fetched `origin/main` was `a2a93db`. The development branch contained
24 commits absent from main; main contained three manual macOS workflow commits
absent from development. Their workflow implementation matched the development
branch before updating its default source to main. The merged source includes the
API, scheduler/runtime, authenticated Command Center, owner-approved enrollment,
migration 0008, portable workers, macOS packaging, both Actions workflows and docs.

## Source-control review

- Reviewed the pending API, model, login return, enrollment UI/bridge, migration,
  integration tests, README and operational reports, plus the complete source
  inventory and the remote workflow changes.
- Credential-pattern scans of the candidate files and unpushed history found no
  provider tokens, private keys or actual Google OAuth client IDs. Credential URLs
  flagged in tests are deliberately invalid fixtures.
- Sanitized the first-worker report to omit personal identities, private addresses,
  production identifiers, exact network policy and production data. Its original
  remains under ignored private `.cache` evidence.
- Strengthened `.gitignore` for OAuth credential filenames, private key containers,
  local databases, logs and generated installers. Verified environment/credential
  files, caches, tools, dependencies, builds and release artifacts stay ignored.
- Updated the manual macOS workflow and its instructions to use main by default.
  It remains manual, uses read-only repository permissions, uploads development
  artifacts only, and performs no application deployment or release publication.

## Checks executed for synchronization

| Check                                            | Result                                                                      |
| ------------------------------------------------ | --------------------------------------------------------------------------- |
| Python Ruff format and lint                      | Passed, 152 files formatted                                                 |
| Strict mypy                                      | Passed, 99 source files                                                     |
| Native Windows pytest                            | 192 passed; 172 database cases deferred to the separate real PostgreSQL run |
| Complete current-source PostgreSQL suite         | 364 passed, zero skipped, 95.27 seconds                                     |
| Dashboard Prettier, ESLint and strict TypeScript | Passed                                                                      |
| Dashboard component tests                        | 9 passed                                                                    |
| Next.js production compilation                   | Passed, including worker enrollment                                         |
| GitHub Actions syntax with local actionlint      | Passed                                                                      |
| Local Compose configuration                      | Passed                                                                      |
| npm dependency audit                             | Zero reported vulnerabilities                                               |
| Git whitespace and exclusion checks              | Passed                                                                      |

The PostgreSQL run mounted current source read-only into the existing local test
image and used only the guarded disposable `godfather_test` database. It exercised
actual FastAPI, SQLAlchemy, migrations, authorization, enrollment races, scheduler,
checkpoint/failover and persistence behavior. Google's upstream service is mocked
by the existing OIDC harness; this does not establish fresh real Google acceptance.
No normal application or production database was migrated by this synchronization.

Previously recorded native ARM64/Intel candidate builds remain documented in the
[macOS Actions report](macos-worker-actions.md). They were not rebuilt here. Apple
signing/notarization, physical recipient acceptance and production enrollment
deployment remain separate work. No production system was accessed or changed.
