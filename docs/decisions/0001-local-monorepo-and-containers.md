# ADR 0001: Local monorepo and coordinator containers

- Status: Accepted for the approved Phase 01 scope
- Date: 2026-10-15

## Context

One developer builds the platform for two founding administrators and needs a repeatable Windows/macOS/Linux development environment. The second administrator does not need a development environment. Production is planned for an independent Ubuntu DigitalOcean coordinator. Initial development requires no cloud infrastructure or new hardware. Phase 01 permits environment tooling and a dashboard shell, with no application features.

## Decision

Use one Git repository, a uv Python workspace, and npm workspaces. Use a single Next.js dashboard and reserve `apps/api` for one modular-monolith FastAPI control plane. Phase 01 creates only its installable Python package scaffold; FastAPI and persistence code start in Phase 02.

Use one Compose configuration for the local dashboard shell, PostgreSQL, and transient Redis. The dashboard's multi-stage standalone image establishes the container packaging model. Later API code joins this architecture; production reuses application images with separately reviewed environment configuration. The local Compose file is not a production deployment recipe.

The Docker build sets `GODFATHER_CONTAINER_BUILD=1` to select standalone output. Native builds use normal Next.js output so `npm start` works without standalone-output warnings or manual asset copying.

Use workspace lockfiles, Python 3.14, and Node.js 24.22.0. Keep Python syntax compatible with 3.12+ and verify the advertised baseline in CI. npm avoids adding another package-manager dependency. Ruff, pytest, and mypy supply Python quality checks. Prettier, ESLint, TypeScript and Next.js builds supply frontend checks. Hatchling only builds the Python scaffold package.

Use ESLint 10, typescript-eslint, and React Hooks rules. The current Next.js ESLint preset brings an unpatched `braces` advisory through its glob dependency chain and React plugins restricted to ESLint 9. Avoid that preset rather than downgrade the application, force incompatible peers, or suppress advisories. Reconsider it when a compatible maintained preset is available. No Next-specific lint coverage is claimed; Next builds and strict TypeScript remain required.

Implement only a static, responsive shell with dark/light tokens and unavailable states. No workflow framework, worker runtime, auth provider, database ORM, migrations, global UI state library, charts, or remote integration is needed in this phase.

## Consequences

- Docker Desktop/WSL2 is a Windows prerequisite. Missing services block container acceptance, not local scaffold work.
- Native frontend hot reload remains available; container smoke tests validate the intended packaging model.
- Application services are separate processes/containers without speculative microservices or distributed persistence.
- Later simulated workers must work on one machine; this phase documents that contract without implementing it.
- Login is not implemented in the shell. Real authentication and authorization must precede real data, remote access and worker operations.
- Adding tooling dependencies is limited to concrete formatting, lint, type, build and test needs.
