# Release source review and commit proposal - 2026-10-20

**Awaiting explicit user approval to create a local Git commit.** No commit, push,
tag, final release archive, artifact transfer or deployment has been performed.
The proposed coordinator version is **0.1.0-rc.4, Linux AMD64**. This is a release
candidate with remote acceptance still pending, not permission to deploy it.

## Proposed changes

Proposed commit title: `Prepare Phase 10 production release tooling and provenance`.
The exact file set for approval is below. No unrelated files were found.

| File                                                     | Intended change                                                                                                                          |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `.dockerignore`                                          | Exclude environment files, private keys/credentials, caches, release outputs and local tool state from image contexts.                   |
| `.gitignore`                                             | Exclude populated `production.env` files at any depth.                                                                                   |
| `README.md`                                              | Link Phase 10 packaging/readiness documentation and preserve the no-deployment boundary.                                                 |
| `apps/api/src/godfather_api/migrations.py`               | Resolve migrations in the installed production-package layout; preserve the existing development default.                                |
| `infrastructure/docker/api.Dockerfile`                   | Add minimal non-editable production stage and release image overrides; preserve development defaults/targets.                            |
| `infrastructure/docker/dashboard.Dockerfile`             | Accept a digest-pinned Node image for release builds; preserve normal development default.                                               |
| `infrastructure/docker/worker-build.Dockerfile`          | Separate Linux standalone-worker build recipe; no worker included in coordinator runtime.                                                |
| `infrastructure/release/images.lock.json`                | Pin Python, uv, Node, PostgreSQL, Redis and Caddy image inputs by immutable digest.                                                      |
| `infrastructure/release/compose.production.yaml`         | Independent production topology, private persistent volumes/networks, resource/log limits; only Caddy publishes ports.                   |
| `infrastructure/release/Caddyfile`                       | HTTPS hosts, same-origin dashboard bridge, tailnet-only worker routes; no public direct human API or backend-health routes.              |
| `infrastructure/release/production.env.example`          | Empty configuration template, required inputs and canonical host paths; no populated values.                                             |
| `infrastructure/release/scripts/common.sh`               | Shared private environment, release verification and Compose context.                                                                    |
| `infrastructure/release/scripts/install.sh`              | Explicit install/upgrade checks, migrations, image verification and failure ordering; only used under separate deployment authorization. |
| `infrastructure/release/scripts/backup.sh`               | Locked, quiesced PostgreSQL/artifact backup with checksums; no schedule or external storage installed.                                   |
| `pyproject.toml`                                         | Pin/hash the seven isolated Hatchling build dependencies; require their hashes. No application dependency changes.                       |
| `uv.lock`                                                | Record build constraints only; retain existing application/development package versions.                                                 |
| `scripts/release.py`                                     | Immutable archive assembly, Linux AMD64 image builds, clean-source checks before/after building, exact commit and pinned-input manifest. |
| `scripts/check_release.py`                               | Verify release contents/provenance/images and exercise isolated migrations, proxy denials, restore and persistence.                      |
| `scripts/build_worker.py`                                | Separate native standalone-worker candidate packaging; no installation/enrollment/service changes.                                       |
| `scripts/check_google_oidc.py`                           | Allow an existing standalone worker executable in the isolated integration harness; Google mocking remains explicitly disclosed.         |
| `tests/test_release.py`                                  | Packaging, checksum/path integrity, secret exclusions, dirty-source refusal and immutable-image-input regression tests.                  |
| `docs/decisions/0009-source-free-production-releases.md` | Explain source-free delivery, independent workers, private networking, storage and provenance decisions.                                 |
| `docs/operations/production-release.md`                  | Clean build, validation, manual installation/backup/recovery procedures, `/opt/the-godfather` paths and rc.4 examples.                   |
| `docs/operations/worker-distribution.md`                 | Separate worker distribution/signing and still-unimplemented single-use enrollment plan.                                                 |
| `docs/operations/release-validation-2026-10-20.md`       | Preserve historical dirty rc.3 candidate results and limitations; not evidence for the new clean release.                                |
| `docs/operations/server-preparation-2026-10-20.md`       | Preserve prior authorized host-preparation evidence; formatting normalized.                                                              |
| `docs/operations/production-readiness-2026-10-20.md`     | Preserve configuration review, exact DNS/OAuth/firewall operator actions and remaining gates.                                            |
| `docs/operations/release-source-review-2026-10-20.md`    | This approval proposal and pre-commit validation record.                                                                                 |

No application schema, Google authentication behavior, roles, ownership, worker
protocol, scheduler, lease/fencing or BYOK feature is being changed.

## Sensitive/temporary/production suitability review

- Manual inspection and a credential-pattern scan found no credentials, private
  keys, bearer tokens, real Google identities, customer records or other private
  user data in the proposed files. An additional scan compared actual sensitive
  values from the ignored local `.env` without displaying or saving those values;
  no proposed file matched. Only the empty production environment template is new.
- `.env`, populated `production.env`, `.cache`, `.tools`, `.venv`, `node_modules`,
  release archives and local validation artifacts remain excluded from the commit.
  Do not use `git add .`; stage the explicit approved file list and inspect the
  staged diff again before committing.
- Temporary QA helpers, disposable test configuration and local fingerprints/logs
  are under ignored `.cache/release-preflight/`. They are not release inputs or
  proposed commit contents. Old dirty rc.1-rc.3 archives remain untouched in ignored
  `dist/` as historical evidence; none is the final release.
- The server/readiness reports contain the public Droplet IPv4 and root SSH command
  examples as operational documentation, without passwords/keys/authentication
  material. The repository remains private. These reports are not bundled into
  the coordinator runtime or archive; INSTALL.md/WORKERS.md are the selected guides.
- Worker archives remain unsigned candidates; their native installers, complete
  worker build-tool lock, secure enrollment/storage and physical macOS acceptance
  are unfinished. No new worker binary is being certified by this coordinator release.
- The pinned uv version supports hash-verified build constraints using an
  experimental feature. The setting is deliberate and must remain covered by the
  container-build/regression gate; a uv upgrade requires renewed validation.
  See [uv build constraints](https://docs.astral.sh/uv/reference/settings/#build-constraint-dependencies).
- Reproducibility means committed source, locked application/build dependencies and
  immutable container inputs. Byte-identical archives/images are not promised:
  archive timestamps/build metadata can differ. Delivered hashes identify the exact
  artifact. Real Google/TLS/Tailscale, backup policy and remote failover gates remain
  open as recorded in the readiness checklist.

## Validation and preservation

| Pre-commit check                                                                         | Result                                                                                                                                                  |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python format / Ruff / strict mypy                                                       | Passed; 124 formatted files and 84 typed source files.                                                                                                  |
| Native Windows pytest                                                                    | 159 passed, 138 PostgreSQL-only skips.                                                                                                                  |
| Complete PostgreSQL-backed regression                                                    | 297 passed, zero skips, 61.75 seconds; final build constraints used.                                                                                    |
| Release unit tests                                                                       | 11 passed within both suites, including dirty-source refusal and mutable-image rejection.                                                               |
| Frontend formatting / ESLint / strict TypeScript / component tests / build               | Passed; 7 component tests.                                                                                                                              |
| Production Compose / offline Caddy / three shell scripts                                 | Passed; no listener, certificate request or production startup.                                                                                         |
| Proposed-file secret scan / explicit exclusions / patch whitespace                       | Passed; no sensitive values printed.                                                                                                                    |
| Existing development preservation                                                        | Passed; same four healthy container IDs, unchanged application-data fingerprint, `.env`, `compose.yaml`, npm lock and Python environment configuration. |
| Dependency versions                                                                      | All 52 existing `uv.lock` package records unchanged; only build constraints added.                                                                      |
| Final clean archive / manifest / archive checksums / production-image restore validation | Pending commit approval; no final archive or commit exists yet.                                                                                         |

Ignored local evidence: `.cache/release-preflight/regression-native.log`,
`regression-database.log`, `preservation.json` and `review.json`. The final database
run used disposable project `godfather-regression-6c33622394fc`; its containers,
network and volume were removed. Development volumes were never test targets.

An initial Markdown format check found the existing server-preparation report
unformatted; it was corrected. Hash enforcement then correctly refused the
unconstrained dynamic `editables` build helper; it was added to the complete
seven-package build closure before final validation. Neither failure touched the
development database or production server.

Existing development container identities/health, `.env`, `compose.yaml` and a
read-only normalized application-data fingerprint were recorded before testing.
Regression used a separate project/network/volume with no published database port,
and removes only its own disposable resources. `uv.lock` intentionally gains build
constraints; package versions and existing development services/data are preserved.
Final production-image tests must run against the clean archive after commit approval.

## Work remaining after approval

1. Recheck the explicit file set and staged diff for drift/secrets. Create the
   approved local commit only; do not push or deploy.
2. Create a clean detached worktree inside ignored `.cache/`, at that exact commit.
   Build `0.1.0-rc.4` with the production builder. Refuse dirty source, changed
   revisions, reused output versions or mutable image references.
3. Verify manifest `source_dirty=false`, exact approved commit, Linux AMD64 image
   architecture/IDs and the recorded pinned inputs.
4. Verify every internal checksum plus the final archive's SHA-256 sidecar; run
   the isolated production-image migration/proxy/restore/restart verifier.
5. Recheck development preservation and write the final release-readiness report
   outside committed source, with archive location/hash, commit, executed results
   and remaining external acceptance gates. Stop; no push/transfer/deployment.
