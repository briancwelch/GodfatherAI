# Documentation

Start with the [user guide](../README.md) for sign-in, worker installation, models
and your first job. The current published coordinator and desktop worker release
is **0.8.0-rc.1**; the [release verification](operations/shared-inference-deployment-2026-10-22.md)
records what was actually checked.

## Using the platform

| Task                                            | Guide                                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Invite people and sign in                       | [User onboarding](operations/user-onboarding.md)                                            |
| Install, update and configure Consigliere       | [Worker guide](operations/consigliere-ui.md)                                                |
| Contribute computers to a workspace             | [Simple contribution](operations/simple-contribution.md)                                    |
| Set up local AI and worker updates              | [Worker readiness and workspaces](operations/worker-readiness-and-workspaces-2026-10-22.md) |
| API keys and local coding projects              | [Account and project setup](operations/coding-and-account-setup.md)                         |
| Review and apply coding results                 | [Results and application](operations/results-and-apply.md)                                  |
| Shared inference, dependent tasks and variables | [Distributed Jobs and Tasks](operations/shared-inference-and-tasks-2026-10-22.md)           |
| Images, analytics and reports                   | [Workload instructions](history/phases.md#phase-12)                                         |
| Manage users, workspaces and jobs               | [Command Center management](operations/command-center-management.md)                        |

The worker readiness guide supersedes the older manual Ollama-only setup in the
Consigliere guide. Distributed Tasks is the current name for the task graphs called
Distributed Jobs in older guides; Distributed Jobs now means shared inference.

For shared colors, Bootstrap components, toasts and progress bars, see
[website appearance settings](operations/bootstrap-ui.md).

## Running a Command Center

- [Docker installation, updates and backups](operations/coordinator-installation.md)
- [First administrator sign-in](operations/founder-bootstrap.md)
- [Portable worker packages and Linux/source setup](operations/worker-distribution.md)
- [Latest production/package verification](operations/shared-inference-deployment-2026-10-22.md)
- [Cleanup and six-release retention](operations/project-cleanup-2026-10-22.md)

## Development and history

- [Development setup and checks](development.md)
- [Consolidated phase history and acceptance evidence](history/phases.md)
- [Repository instructions](../AGENTS.md) and [UI/UX rules](design/UI-UX.md)
- [Architecture](architecture/) and [decision records](decisions/)
- [Versioned protocols](protocols/)

Dated deployment and verification reports remain under `operations/` as historical
evidence. Their release numbers, authorization and test counts apply to those
specific runs. Use the current user/operator guides for new installations.
