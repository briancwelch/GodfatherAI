# Phase 01: Repository and environment

## Authorized scope

Git monorepo, locked uv/Python and npm/Next.js dependencies, formatting/lint/typing/tests, local environment template, Compose dependencies and shell image, CI configuration, cross-platform setup and compatibility documentation. The dashboard is nonfunctional and local only.

No Phase 02 routes, health endpoints, configuration system, logging pipeline, SQLAlchemy models, migrations, or application persistence are implemented. No worker, scheduler, inference, agent workflow, failover, functional management UI, private-data use or public hosting is implemented.

## Gate

The sole developer can clone, restore dependencies, start the local Linux-container stack, open `http://localhost:3000`, and pass checks using repeatable setup instructions. The platform has two administrators, not two developers; the second administrator does not need a development environment. PostgreSQL data persists across container recreation. Workers and other later features will be testable with multiple simulated processes on one machine when their phases are implemented.

## Initial scaffold validation

These records describe the initial, pre-reboot checks. Current Docker/WSL2 results follow in the next section.

Validated locally on Windows x64 on 2026-10-15, with project-managed Python 3.14.8, uv 0.13.1, Node.js 24.22.0, npm 11.19.1, and Edge 155.0.4283.45.

| Check                                 | Actual result                                                                                                            |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Private GitHub repository             | GitHub metadata confirms `briancwelch/GodfatherAI` is private and empty; local `origin` configured                       |
| `uv sync --all-packages`              | Passed; `uv.lock` generated and local package installed                                                                  |
| `npm install`                         | Passed; root workspace lockfile generated                                                                                |
| Portable `scripts/dev.py check`       | Passed end to end after initial test typing corrections                                                                  |
| Ruff format/check                     | Passed                                                                                                                   |
| Strict mypy                           | Passed, four source files                                                                                                |
| pytest                                | Seven tests passed                                                                                                       |
| Prettier                              | Passed                                                                                                                   |
| ESLint 10                             | Passed, zero warnings                                                                                                    |
| TypeScript/Next route type generation | Passed                                                                                                                   |
| Next.js native production build       | Passed; static shell and icon generated                                                                                  |
| Native production server              | Running on `127.0.0.1:3000`; HTTP 200                                                                                    |
| Edge desktop, 1440×1000               | Light/dark passed; screenshots inspected                                                                                 |
| Edge narrow layout, 390×844           | Light/dark passed; screenshots inspected                                                                                 |
| Browser smoke behavior                | Skip link, keyboard phase anchor, collapsible narrow navigation, no horizontal overflow or console errors                |
| HTTP response headers                 | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` observed                                                      |
| `npm audit --audit-level=high`        | Zero reported vulnerabilities after replacing the Next lint preset                                                       |
| Compose client `config --quiet`       | Passed using checksum-verified Compose 5.6.0, with a disposable validation password supplied through process environment |
| Missing PostgreSQL password           | Configuration correctly rejected, exit 1                                                                                 |
| Official image manifests              | Selected Node, PostgreSQL and Redis tags advertise Linux amd64 and arm64                                                 |
| Git ignore rules                      | Local environment, tooling, dependencies, caches and build output excluded                                               |
| Development doctor                    | Expected failure: Docker CLI/engine prerequisites missing                                                                |

Browser automation used isolated headless Edge contexts after the browser tool's sandbox helper failed. The one-off smoke probe and screenshots are under ignored `.tools` and `.cache`; no browser test dependency was added to the project. This is a focused layout/keyboard check, not a full accessibility audit or actual mobile-device test.

The initial Windows inspection found no Docker Desktop/CLI installation and WSL reported not installed. The owner subsequently installed Docker Desktop for all users with its WSL2 backend and rebooted. The authorized post-reboot checks below supersede the initial Docker prerequisite failure.

CI definitions cover Python and frontend checks on Windows/macOS/Linux and container health/persistence on Linux. They are not completed runs until the repository is pushed and GitHub Actions executes with authorization.

`AGENTS.md` now explicitly records the owner's clarification: one developer builds the platform for two equal founding administrators. The shell copy, README, ADR and phase gate use the same distinction. `docs/design/UI-UX.md` remains unchanged, including its pre-existing trailing space.

## Post-reboot Docker/WSL2 validation — 2026-10-15

| Check                       | Actual result                                                                                                                                                                |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| WSL                         | Default version 2; `docker-desktop` running on WSL2                                                                                                                          |
| Docker Desktop              | 4.95.0; client/server engine 29.8.2, `desktop-linux`, Linux amd64                                                                                                            |
| Docker Compose              | 5.6.0 from the installed Docker Desktop                                                                                                                                      |
| Local configuration         | Created ignored `.env` with a unique generated local password; no credential was printed or committed                                                                        |
| Fresh dashboard image build | Passed using the Linux standalone build/runtime stages                                                                                                                       |
| Full stack startup          | `docker compose up --build --wait --wait-timeout 180` passed; dashboard, PostgreSQL and Redis healthy                                                                        |
| Local URL                   | `http://localhost:3000` returns HTTP 200 from the dashboard container                                                                                                        |
| Port isolation              | Only `127.0.0.1:3000` published; PostgreSQL/Redis host bindings absent                                                                                                       |
| Backend network             | `internal=true`; dashboard and database/cache use separate networks                                                                                                          |
| Runtime restrictions        | Dashboard uid 1000 and Redis uid 999; both read-only root filesystems                                                                                                        |
| Redis                       | `PING` returned `PONG`                                                                                                                                                       |
| PostgreSQL persistence      | Committed a scratch value, recreated only the PostgreSQL container, confirmed a changed container ID and the surviving value; removed only the test-created table afterwards |
| Dependency lock cleanup     | Deduplicated old ESLint peer installations; the rebuilt container uses ESLint 10 without the old deprecation warning                                                         |
| Environment doctor          | Passed with Linux engine and all required tools available                                                                                                                    |
| Full local check runner     | Passed after the team-copy and lockfile changes: Ruff format/lint, strict mypy, seven pytest tests, Prettier, ESLint, strict TypeScript and native Next.js build             |
| npm audit                   | Zero reported vulnerabilities                                                                                                                                                |
| Container browser smoke     | Isolated Edge at 1440×1000 and 390×844, light and dark; all four cases passed HTTP, keyboard anchors, narrow navigation, overflow and console-error checks                   |

Local containers are intentionally left running for review. Stop them with `docker compose down`; preserve the named PostgreSQL volume. No host service installation, public deployment or external integration was performed by this verification.

## Gate completion before Phase 02

- Published as `9176cb00184e91b3e3df737c62285a862ef3feb7` to the authorized private repository.
- [All eight GitHub CI jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/38831542451), including Windows/macOS/Linux checks and Linux container health/persistence.
- A clean private-repository clone restored locked Python/npm dependencies and passed its complete check runner.
- Repeated local Docker startup and PostgreSQL container-recreation persistence passed. Redis temporary state was correctly discarded on recreation, followed by a successful PING.
- One developer/two administrators remains the team model. GPU and physical worker validation belong to later phases; CI does not prove every physical hardware/backend combination.

The Phase 01 gate passed before beginning the explicitly authorized Phase 02. See `phase-02.md` for current API configuration and commands.

## Stop condition

Report completed work and remaining acceptance gaps, then stop. Phase 02 requires explicit approval. Cloud deployment, DNS changes, remote service installation and production credentials remain separately gated.
