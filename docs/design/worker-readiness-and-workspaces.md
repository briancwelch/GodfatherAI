# Worker readiness and workspace navigation

Owner-authorized milestone, 2026-10-22. Deployment requires a separate approval.

## Screen purpose and hierarchy

- Overview summarizes all workspaces visible to the signed-in account, node health,
  recent work and activity. Create workspace is a primary action.
- Workspaces lists every authorized workspace before opening a workspace-scoped
  overview. Membership and ownership continue to define visibility.
- Images and Analytics and Reports are distinct workflows. Each has a collapsible
  right-hand worker-readiness panel; narrow screens stack the panel below the form.
- Account settings is available to every signed-in invited user: display name,
  avatar, optional shared location and private AI connections. Admin settings is
  visible and accessible only to platform administrators.
- Nodes and the desktop worker show Update Available separately from connection
  status. The desktop checks its configured HTTPS coordinator's verified downloads.

## Components and states

Reuse application shell, tables, badges, forms and notices. Workspace lists have
loading, empty, permission-denied, stale and error states. Profile changes show
confirmed save or a meaningful error. Small account avatars have a branded initials
fallback. Readiness panels distinguish disconnected, missing runtime, missing model,
installation requested, failure and discovered readiness.

Updates prompt by default; an owner-local preference permits unattended updates.
Only idle workers hand off to the native installer. Hash, platform and version
checks precede execution. Credentials, node identity, projects and consent survive.
Runtime provisioning and model downloads require independent owner consent and
remain local to the selected worker; no public Ollama endpoint or paid fallback.

## Data and permission boundaries

PostgreSQL remains authoritative. Overview aggregation includes only accessible
workspaces. Profile writes always target the authenticated user. Platform settings
retain backend authorization. Worker installation requests are owner-scoped and
require local host consent; platform administration never grants host permissions.
Download artifacts are selected from a trusted manifest, never job-supplied URLs.

## Acceptance checklist

- Old worker versions show Update Available; unknown and newer versions do not.
- Corrupt, redirected, wrong-platform or downgraded downloads never execute.
- Updates preserve connection/settings and wait for active work to finish.
- A new worker can explicitly set up local inference and request a catalog model.
- Overview aggregates visible workspaces; selecting one scopes its overview.
- Workspace creation is available directly from Overview and Workspaces.
- Non-admin accounts can edit their profiles and cannot access Admin settings.
- Profile preferences survive Google sign-in; avatars have a 16 px fallback.
- Both workload workflows retain validation and expose collapsible setup guidance.
- Keyboard focus, expanded state and responsive stacking remain accessible.
