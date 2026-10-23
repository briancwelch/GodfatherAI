# Development setup

Use this guide for a local source checkout on Windows, macOS or Linux. The local
Command Center is **http://127.0.0.1:3000**. For ordinary platform use, start with
the [user guide](../../README.md); for a packaged Linux coordinator, use
[coordinator installation](coordinator-installation.md). The
[consolidated phase history](../history/phases.md) contains earlier acceptance
commands and results, rather than current milestone instructions.

Apply all current migrations through the migrate service before starting a changed
API schema. Preserve database/artifact volumes and an existing `.env`. Configure
Google Sign-In and the [one-time founder setup](founder-bootstrap.md) for normal
browser use. Existing identities require explicit ownership-preserving linking.
Local setup does not authorize public exposure or changes to contributor hosts.

## Supported baseline

| Component | Baseline                                                                              |
| --------- | ------------------------------------------------------------------------------------- |
| Python    | 3.14 selected by uv; source syntax minimum 3.12                                       |
| uv        | 0.13.1 (also pinned in CI)                                                            |
| Node.js   | 24.22.0 (`.node-version`)                                                             |
| npm       | 11.x; use the root workspace and committed `package-lock.json`                        |
| Docker    | Supported Docker Desktop or Docker Engine, Linux containers                           |
| Compose   | `docker compose` with `up --wait` support; version 2.20+ or a supported newer release |

Install tools from official sources after the machine owner approves installation. No repository script installs services, alters PATH, enables virtualization, creates GitHub resources, or configures cloud systems.

## Windows 11, VS Code, and PowerShell

1. Confirm hardware virtualization is enabled. Install/update WSL2 with machine-owner authorization; this may require administrator privileges and a reboot.
2. Install Docker Desktop, select its WSL2 backend, and use Linux containers. Start Docker Desktop manually. Docker Desktop licensing terms apply.
3. Install Git, Node.js 24.22.0 with npm 11, and uv 0.13.1. Keep existing system Python if other projects need it. Open a fresh terminal after installation.
4. Authenticate Git through your normal GitHub credential manager, then clone:

   ```powershell
   git clone https://github.com/briancwelch/GodfatherAI.git
   Set-Location GodfatherAI
   ```

5. Restore dependencies and create local configuration:

   ```powershell
   uv python install 3.14
   uv sync --locked --all-packages
   npm.cmd ci
   Copy-Item -LiteralPath .env.example -Destination .env
   ```

   Edit `.env` and replace the password placeholder with a unique local password before starting containers. The file is ignored by Git. Do not reuse production credentials. Do not overwrite an existing `.env` when repeating setup.

6. Inspect prerequisites and start locally:

   ```powershell
   uv run --locked --all-packages python scripts/dev.py doctor
   docker compose config --quiet
   docker compose --profile tools build dashboard api migrate
   docker compose up --wait postgres redis
   docker compose --profile tools run --rm migrate
   docker compose up --wait
   ```

7. Open **http://localhost:3000** for the shell and **http://localhost:8000/api/v1** for the API. Run checks:

   ```powershell
   uv run --locked --all-packages python scripts/dev.py check
   ```

`npm.cmd` avoids PowerShell execution-policy restrictions on the `npm.ps1` shim. The portable check runner resolves the Windows shim itself. No PowerShell 7 or Bash dependency is required. VS Code should use `.venv\Scripts\python.exe` and the workspace TypeScript version.

## macOS (Apple Silicon or Intel)

1. Install Git/Command Line Tools, native Node.js 24.22.0 with npm 11, and uv 0.13.1 using approved installation methods.
2. Install and start the appropriate Docker Desktop build for your CPU. Do not force `linux/amd64` on Apple Silicon.
3. Clone and prepare:

   ```sh
   git clone https://github.com/briancwelch/GodfatherAI.git
   cd GodfatherAI
   uv python install 3.14
   uv sync --locked --all-packages
   npm ci
   cp .env.example .env
   ```

4. Replace the local password placeholder in `.env`. Preserve an existing `.env` on subsequent runs.
5. Run the doctor, Compose, and check commands from the Windows section (use `npm` for manual npm commands). Open **http://localhost:3000**.

Use `.venv/bin/python` in VS Code. macOS support is a portability target; local Windows verification is not evidence of a physical Mac test.

## Linux (Ubuntu recommended)

1. Install Git, Node.js 24.22.0 with npm 11, uv 0.13.1, Docker Engine, and the Compose plugin using approved installation methods. Start the Docker service with explicit owner authorization.
2. Ensure your user has appropriate Docker access. Docker daemon access grants substantial host privileges; do not silently add users to privileged groups.
3. Follow the macOS clone, restore, and `.env` steps.
4. Run the doctor, Compose, and check commands. Open **http://localhost:3000** on the development host.

This is a development guide, not authorization to install on a VPS or expose services remotely. No cloud resources are required.

## Daily workflow

Restore with `uv sync --locked --all-packages` and `npm ci` after pulling dependency changes. Use one application mode at a time:

| Mode                 | Commands                                                      | Use                                                                 |
| -------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------- |
| Container smoke test | Follow the explicit build/migrate/start sequence above        | Same application container model intended for the Linux coordinator |
| Native hot reload    | `docker compose up --wait postgres redis`, then `npm run dev` | Frontend editing on Windows/macOS/Linux                             |

To switch to native mode, run `docker compose stop dashboard` before `npm run dev`. To stop the local stack, use `docker compose down`; the PostgreSQL named volume remains. Do not use volume deletion flags or reset a database without explicit authorization.

The dashboard uses the local authenticated API. PostgreSQL remains on the internal
backend network; the dashboard receives no database credentials. Redis is
transient. Current regression tests cover worker health, scheduling, workflow
recovery and authorization. Historical phase demonstrations remain in the
[phase record](../history/phases.md). Always apply reviewed migrations explicitly
before starting a changed API schema.

Before review, run:

```text
uv run --locked --all-packages ruff format --check .
uv run --locked --all-packages ruff check .
uv run --locked --all-packages mypy
uv run --locked --all-packages pytest
npm run format:check
npm run lint
npm run typecheck
npm run build
docker compose config --quiet
```

Use `uv run --all-packages ruff format .` and `npm run format` to format intentional changes. Builds and lint are separate checks. Review the diff before committing. Do not commit `.env`, caches, interpreters, dependencies, or build outputs.

## Troubleshooting

- **Docker is missing or unavailable:** finish the authorized Docker/WSL setup and start the Linux engine. Native shell development still works, but the container acceptance gate remains pending.
- **Port 3000 in use:** stop the existing dashboard process/container before starting another. Do not terminate unrelated processes.
- **Git dubious ownership in an automated sandbox:** use a command-scoped `git -c safe.directory="D:/Projects/Godfather AI" ...` exception for this verified directory. Do not disable ownership checks globally.
- **Offline or restricted network:** first-time dependency restores and image pulls need network access. Do not substitute unlocked dependencies or report unexecuted checks as passing.
- **PostgreSQL password changed after volume initialization:** changing `.env` does not change the stored database password. Preserve the volume and explicitly plan a credential change; do not delete data as a shortcut.
- **Compose environment error:** set `POSTGRES_PASSWORD` in ignored `.env`. Avoid printing resolved Compose configuration when it contains credentials; use `config --quiet`.
- **Apple Silicon/native module failures:** use an arm64 Node/Python installation and rerun the locked restore. Do not copy `node_modules` or `.venv` from another OS or architecture.

Official references: [uv installation](https://docs.astral.sh/uv/getting-started/installation/), [Docker Desktop on Windows](https://docs.docker.com/desktop/setup/install/windows-install/), [Docker Desktop on macOS](https://docs.docker.com/desktop/setup/install/mac-install/), [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/), [Next.js installation](https://nextjs.org/docs/app/getting-started/installation).
