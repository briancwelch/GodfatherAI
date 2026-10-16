# Phase 07–08 Command Center design

Authorized as one combined milestone. Phase 09 and BYOK remain out of scope.

## Screens and hierarchy

The trusted local administrator connects with an existing provisioned administrator
credential. A same-origin server bridge validates it against the API and keeps it in
an HttpOnly, SameSite=Strict cookie with an eight-hour lifetime. It is never stored
in JavaScript storage or included in client bundles. Every API request revalidates
the credential and existing workspace permissions. This is a local credential
bridge, not production login or Phase 09 RBAC.

Persistent navigation: Overview, Jobs, Nodes, Agents, Models, Activity. Other
administration screens remain outside this milestone. Workspace selection scopes
jobs, agents, models and audit data. Node health uses existing platform-admin scope.

- Overview: full-scope counts, real resource readings, recent jobs and failovers.
- Nodes: searchable health/platform table; identity, owner, resources, permissions,
  active jobs and scoped activity in an inspection panel; confirmed drain/disable.
- Jobs: submit a pinned read-only agent workflow or synthetic job; searchable
  status table; attempts, checkpoint progress, artifact references, errors, result
  and chronological recovery history. Cancellation and eligible retry are confirmed.
- Agents: immutable definitions/versions, requirements, tool grants, model selection,
  execution history, confirmed enable/disable using existing API operations.
- Models: provider-neutral deployment table, hosting node, availability, capability
  provenance, known context/memory estimates and observed inference usage.
- Activity: node, actor, job, agent, type, severity and UTC range filters; timestamps
  displayed in browser-local time; safe durable event details.

## Components and states

Shared page header, summary cards, semantic status badge, scrollable data table,
filter controls, inspection panel, native confirmation dialog, JSON disclosure,
loading/empty/error/permission-denied/stale status. Poll every three seconds while
visible, without overlapping requests; retain visibly stale data after refresh
failure. Counts come from PostgreSQL, never from a truncated table page. Bounded
lists show limits and paging. Unknown telemetry is distinct from zero; simulated
readings are explicitly labeled and excluded from physical utilization summaries.

Use existing light/dark tokens and shadcn button. Responsive sidebar becomes a
wrapping navigation on narrow screens. Tables scroll within their own region.
Semantic headings, labeled fields, visible focus, keyboard links/buttons, native
modal focus trapping, Escape dismissal and live status/error announcements support
accessible inspection. Detailed JSON is secondary to named operational fields.

## Data and security dependencies

Reuse `/nodes`, `/jobs`, workflow/agent/model APIs and add scoped command-center
summary/workspace/event reads in the same FastAPI monolith. Add bounded manual retry
to the existing job lifecycle, preserving attempts, checkpoints and fences. No
second scheduler, database, cloud storage or inference system. Browser proxy paths
are allowlisted; mutations require matching Origin and loopback Host. No global
administrator token impersonates all browser users. No production deployment.

## Acceptance checklist

- Real registrations and health appear; simulations and unavailable telemetry are clear.
- A workflow submitted in the browser produces real backend job/attempt/checkpoint data.
- Stopping its worker yields interruption, fencing, compatible reassignment, resume
  and completion with linked original/recovery attempts and no repeated committed step.
- Stale writes, incompatible OS/resources/tools/models and unauthorized workspaces fail closed.
- Cancel/retry/drain/disable/agent controls require confirmation and backend success.
- Empty, loading, disconnected, unauthorized, light/dark and narrow layouts are usable.
- Frontend lint/type/build, component checks, PostgreSQL and browser acceptance pass.
