# Command Center desktop workspace and agent management

This assignment authorizes the Command Center redesign, agent management, a clean
production build and deployment to the existing Droplet. BYOK remains planning only.

The shared shell uses The Godfather branding, Core `#14283D`, Ion `#58D5DE`, Ion Ink
`#087F8C` and Chalk `#F4F8FC`. Section tabs, grouped ribbons, compact tables,
collapsible/resizable utility panels and a bottom connection status bar follow
the supplied desktop application references. Light and dark views are available.
Unavailable commands explain their requirements on hover or keyboard focus.

Select a workspace, open Agents and choose Create agent. Workspace administrators
can configure a name, description, advertised model/capabilities, permitted tools
and a supported sequential workflow. Edit / New version always saves a new
immutable version; it never rewrites a running job's configuration. Custom steps
use the existing v1 runtime contract. Workspace selection precedes creation so
the editor's model/tool catalog is scoped to that workspace. Creation needs an
advertised permitted model; unavailable deployments remain marked unavailable.

Select an agent row to inspect its configuration, execution history and results,
change version availability, or Run agent. Run submits to the existing durable
scheduler and opens the job's live progress, checkpoints, attempts and results.
No compatible worker means the job waits in the queue. Workflow execution still
requires a worker explicitly advertising workflow protocol v1 and owner grants.
The editor does not install models, grant node permissions or enable paid inference.

Models → Add model opens a selection-based installer. Choose an owned worker,
its advertised Ollama runtime and a catalog model, then explicitly confirm the
download. The worker owner must first opt in locally with
`--allow-model-installation` alongside its existing `--inference-config`. Run
agents additionally requires the existing `--execute-workflows` opt-in. Model
installation does not grant arbitrary tools; `--allow-tool` and tool permissions
remain independent. Existing worker IDs, credentials and provider files are reused.
No model is downloaded merely by opening the directory or creating an agent.

Workspace policies use model/tool checkboxes and known accounts use selection
lists. Activity filters use available node/job/agent/event choices. Advanced
custom sequential steps remain optional JSON; standard text/plan workflows and
ordinary model selection use forms.

`GET /api/v1/agent-options?workspace_id=UUID` returns authenticated, workspace-scoped
model and tool choices plus visible capability advertisements and supported runtime
templates. Model options are bounded to the first 200 permitted deployments.
The authenticated snapshot exposes the configured backend environment, independent
of the browser hostname. Agent history includes the latest 100 durable jobs across
its versions. Existing authentication, workspace isolation and execution fencing
remain authoritative. No schema migration or new runtime dependency is introduced.

Acceptance covers creation, immutable versions, enable/disable, actual model
execution, progress/results, workspace denial, node-owner restrictions and session
revocation. Automated provider fixtures are restricted to the disposable test
environment; they do not establish real Google account acceptance in production.

## Deployment and executed checks — 2026-10-20

- Coordinator `0.1.0-rc.7` deployed to the existing Droplet at
  `https://app.the-godfather.ai`; API/dashboard containers are healthy.
- Source revision `f0b7519`; archive SHA-256
  `98b383a314939fe2cf7b3127e216863b0e676eb9bd4e92da218855e6f2b2235b`.
- Paired backup: `/opt/the-godfather/state/backups/20261020T211924-62563`.
  PostgreSQL/Redis containers, volumes and production environment were preserved.
  Schema remains `0007_founder_bootstrap`; no migration was needed. Identity,
  workspace, node and existing job/result fingerprints matched after deployment.
- Carbon reconnected under its original identity with worker `0.1.0-rc.3`, workflow
  v1 and model-installation opt-in. Its credentials/provider files and prior binary
  were retained. No model was downloaded during this assignment.
- Passed: 331 clean-source Python/PostgreSQL tests, nine frontend component tests,
  Ruff, mypy, TypeScript, ESLint, production builds and disposable release
  image/migration/backup/restore checks. Browser acceptance used the packaged
  Windows worker and real installed `qwen3:8b`, covering agent creation/versioning,
  enable/disable, execution/results/checkpoint, model selectors, isolation,
  revocation and a 390px dark layout. Only Google network responses were mocked
  inside that isolated test.
- Live HTTPS, shell, anonymous API denial and actual Google OAuth redirect with
  the production callback/PKCE passed. Final authenticated production creation/run
  acceptance awaits the owner's normal browser session; browser-control startup
  was unavailable. No production session or operational record was fabricated.
