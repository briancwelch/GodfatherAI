# Local release preparation results - 2026-10-20

Only local packaging and tests were authorized. No SSH connection, Droplet change,
cloud resource, DNS change, Google account configuration, public certificate request,
service installation or model download was performed. Phase 10 remote acceptance
is **not complete**. The development Compose configuration and `.env` were preserved;
the four development services remain healthy, with PostgreSQL at `0006_google_identity`.

## Final delivery artifacts

Paths are relative to the development checkout. Each archive also has its extracted
directory beside it. Earlier coordinator rc.1/rc.2 and Windows-worker rc.1 candidates
remain in `dist/` as superseded local build evidence; use the final artifacts below.

| Artifact                                           | Size, bytes | SHA-256                                                            |
| -------------------------------------------------- | ----------: | ------------------------------------------------------------------ |
| `dist/godfather-0.1.0-rc.3-linux-amd64.tar.gz`     |   301505402 | `f16ee432156bd01bd0eea2341de7b272a051df0e86d8820dc090330676c15108` |
| `dist/godfather-worker-0.1.0-rc.2-windows-x64.zip` |    14055403 | `573a33811f0058d8fbaba15b61e82b3f0c18bf2b6d32d572884dbba8b0117961` |
| `dist/godfather-worker-0.1.0-rc.2-linux-x64.zip`   |    13738933 | `f7383e30bc23a99f6e3dd162f8581f6fb892adb5e5489825652c10924708512a` |

Each has a matching `.sha256` sidecar. The coordinator directory contains exactly:
`images.tar`, `compose.production.yaml`, `Caddyfile`, `production.env.example`,
`release.env`, `image-ids.txt`, `manifest.json`, `SHA256SUMS`, `INSTALL.md`, `WORKERS.md`,
and `scripts/{common,install,backup}.sh`. Images are `godfather/{api,dashboard,postgres,redis,caddy}:0.1.0-rc.3`,
all Linux AMD64. `images.tar` is 311241216 bytes. Upstream image versions are
PostgreSQL 17.11 Bookworm, Redis 7.4.11 Bookworm and Caddy 2.11.2 Alpine.
Manifest/checksums record exact image IDs and resolved upstream digests.

The manifest honestly records `source_dirty=true` against baseline commit
`4304e4a10dcd24a65610ac78d056a7333e479621`. This is an uncommitted local candidate,
not a published release. Commit/review and rebuild from a clean source revision
before final production release. Nothing was pushed under the local-only authorization.

## Implementation and files changed

- `.dockerignore`: exclude nested environment files, credentials, Git/tool state,
  release outputs and caches from image contexts.
- `infrastructure/docker/api.Dockerfile`: add a clean production stage containing
  non-editable API dependencies and migrations, without worker/development tooling.
  Existing local runtime and development targets remain available.
- `apps/api/src/godfather_api/migrations.py`: explicit migration-directory override
  for installed package layouts; existing source-layout fallback is retained.
- `infrastructure/release/`: separate production topology, private persistent data,
  bounded RAM/CPU/logs, proxy/TLS configuration, empty environment template,
  migration/upgrade/backup scripts and maintenance locks. No public database ports.
- `scripts/{release,check_release,build_worker}.py`,
  `infrastructure/docker/worker-build.Dockerfile`, `tests/test_release.py`:
  immutable coordinator assembly, actual local container verification, native
  worker packaging, and archive integrity/secret-exclusion tests.
- `scripts/check_google_oidc.py`: optional standalone worker executable in the
  existing isolated real-backend browser test.
- README, ADR 0009, production guide and worker distribution/enrollment plan.

No schema, Google auth behavior, role/workspace permissions, node ownership,
worker protocol, machine credential, scheduler or fencing behavior was changed.
Production data is never replaced with test data. Test probes/fixtures were confined
to uniquely named disposable release projects and the guarded `godfather_test` database.

## Executed checks and evidence

| Check                                                                           | Result                                                                                                                                                                                    |
| ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Original local Compose validation/startup                                       | All four services healthy; database has current head                                                                                                                                      |
| Python formatting, Ruff and strict mypy                                         | Passed; 121 formatted files / 84 typed source files                                                                                                                                       |
| Native Windows full pytest                                                      | 156 passed, 138 PostgreSQL-only skips at that run                                                                                                                                         |
| Full PostgreSQL-backed regression suite                                         | 294 passed, zero skips; 62.39 seconds                                                                                                                                                     |
| Final release-specific unit tests                                               | 9 passed, including allowlisted packaging and secret exclusion                                                                                                                            |
| Frontend Prettier, ESLint, strict TypeScript, component tests, production build | Passed; 7 frontend tests                                                                                                                                                                  |
| Runtime npm audit                                                               | Zero reported vulnerabilities using `--omit=dev --audit-level=high`                                                                                                                       |
| Python installed dependency compatibility                                       | 50 packages compatible; this is not a vulnerability scan                                                                                                                                  |
| API/dashboard image audits                                                      | Correct AMD64 target, installed migration path, no worker/dev modules or checkout/environment/Git files in the checked application paths                                                  |
| Production Compose/Caddy and shell syntax                                       | Valid; Caddy validated with networking disabled, without certificate issuance                                                                                                             |
| Isolated production-image verification                                          | Fresh/repeated migrations; five healthy services; real loopback HTTP proxy; anonymous 401; non-tailnet worker 403; public backend-health 404; Redis PONG                                  |
| Database/artifact recovery                                                      | Full custom-format dump restored into a separate disposable database; artifact archive restored into a fresh volume; probe contents matched                                               |
| Persistence/restart                                                             | PostgreSQL container recreated, data retained, API readiness and service health recovered                                                                                                 |
| Installer failure-order fixture                                                 | Failed migration does not start apps or update current release; unapproved Compose image override rejected before startup. Docker is deliberately mocked only in this isolated shell test |
| Standalone Windows worker                                                       | Native help startup; minimal PATH and unrelated working directory startup; actual browser/API/database/model integration passed                                                           |
| Standalone Linux worker                                                         | Built under Docker Desktop Linux/WSL2; startup passed in a PostgreSQL runtime container with neither python nor python3 installed                                                         |
| Patch whitespace                                                                | `git diff --check` passed                                                                                                                                                                 |

The full PostgreSQL run preceded the last additional secret-exclusion unit case;
that new case subsequently passed with the other eight release-specific tests.
Initial new test-harness assertion/profile/type/route issues were corrected and
rerun; they are not outstanding application failures.

Production-image evidence is under `.cache/release-tests/` in per-run `result.json`
and `stats.jsonl` files. The rc.1 complete run is `d94b99f8ee90`; rc.2 is
`a3bb4a4ee237`; final rc.3 is `e03cc00d2982`. These use nonfunctional Google
configuration and **plain loopback HTTP**, not real Google/TLS/DNS acceptance.
All disposable project containers/volumes are removed by the verifier afterward.

Standalone Windows integration evidence:
`.cache/phase09-runs/b01f4f64b22e48b2929306de324cccae/browser-result.json`.
Actual API/PostgreSQL/Next.js/Windows worker/existing Ollama `qwen3:8b` produced
workflow output, checkpoints, artifacts and events. Owner/workspace restrictions,
equal administrators, cancellation, revocation and session behavior passed.
**Only Google HTTP responses were mocked. Real Google login remains unverified.**
The existing Ollama executable was started temporarily on loopback for this test;
only that owned test process and its runner were stopped afterward. No runtime or
model was installed/downloaded, and no provider was enabled for ordinary application use.

## Server sizing and security boundary

Steady service memory ceilings total 2560MiB; migrations use up to 768MiB with
API/scheduler stopped. The first idle Docker Desktop observation totaled about
192MiB (API 100.3, dashboard 44.84, PostgreSQL 31.14, Caddy 11.25, Redis 4.723MiB).
This is not a stress/load test, host-wide measurement or Droplet capacity guarantee.
No inference workloads belong on the 2-vCPU/4GB coordinator. Monitor disk, memory,
database/artifact growth, OOMs, latency and backups on the actual host.

PostgreSQL/Redis stay on an internal network. Only Caddy publishes ports. Browser
sessions retain the existing same-origin bridge and backend authorization. Worker
routes require tailnet source addresses plus machine credentials; actual Linux
source-address preservation and least-privilege Tailscale grants remain unverified.
Secret values exist only in private runtime configuration/worker stores; trusted
root/Docker operators can inspect container environment values. Agree to that
trust model or separately authorize a stronger secret-store integration.

## Outstanding prerequisites and operator decisions

1. Configure the production Google Web client and exact callback, verify bootstrap
   subject/identity mappings, and complete real login/invitation/logout/role acceptance.
2. Verify domain ownership and configure app/API DNS only after authorization;
   validate HTTPS/ACME, host/cloud firewall, trusted SSH access and Tailscale split DNS/grants.
3. Implement/test the documented short-lived single-use enrollment protocol.
   Current machine credentials are reusable and are not enrollment credentials.
4. Produce macOS arm64/x64 builds on appropriate native runners; validate physical
   macOS/Linux operation, remote execution/failover and actual accelerator backends.
5. Choose worker distribution hosting and signing identities. Sign/notarize artifacts;
   implement native per-user Windows/macOS/Linux installers and secure credential stores.
   Current Windows/Linux archives are unsigned standalone candidates, not native installers.
6. Lock the complete worker build-tool dependency graph and produce a final
   license/SBOM inventory; perform API/OS image advisories and production security review.
7. Verify actual Droplet capacity/services/ports and Docker/Compose support. Full SSH
   install/upgrade/rollback and native service lifecycle were not executed here.
8. Select backup retention, encrypted off-host destination, recovery objectives,
   production secret rotation and audit retention. No cron/cloud infrastructure was installed.
9. Review/commit the source changes and regenerate clean release provenance before
   production. Local packaging is complete; the remote Phase 10 gate remains open.

Use [production-release.md](production-release.md) for exact build/test/SSH install,
upgrade, backup, rollback, secret and DNS instructions; use
[worker-distribution.md](worker-distribution.md) for worker commands/native installer
and single-use enrollment design. Stop before any remote action.
