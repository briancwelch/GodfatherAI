# The Godfather: Command Center UI/UX Specification

## Purpose and authority
This document governs the design and interaction of the browser-based Command Center. `AGENTS.md` remains authoritative for architecture, security, implementation phases, and permissions. When the two documents conflict, follow `AGENTS.md` and ask before changing either document. This specification is a design baseline, not authorization to implement later phases.

## Product goals
- Provide a clear, centralized view of the shared Las Vegas / Los Angeles AI cluster.
- Support two equal founding administrators and future limited contributors.
- Make node health, job progress, failover, model capacity, and agent status understandable at a glance.
- Support productive use of the platform, not merely administration: submit tasks, inspect results, and review approvals.
- Be responsive and usable from current desktop browsers on Windows, macOS, and Linux, with tablet support where practical.

## Design principles
1. Operational clarity over visual spectacle. Prioritize actionable information.
2. Honest state. Never fabricate live telemetry; label demonstration data prominently.
3. Progressive disclosure. Overview first, technical detail on demand.
4. Accessible by default: semantic controls, keyboard navigation, visible focus, color-independent status cues, and WCAG 2.2 AA as the target.
5. Consistency: reusable components, spacing, typography, labels, status vocabulary, and confirmation patterns.
6. Performance: minimize unnecessary animation, expensive polling, and dashboard clutter.
7. Responsive layout: desktop-first for dense administration, graceful narrow-screen behavior.
8. Security in the UI: clearly show scope, ownership, permissions, and consequences before sensitive actions. Enforce permissions in the backend, never only in the UI.

## Design system
- Current authorized desktop direction: navy Core `#14283D` application bar, Ion
  `#58D5DE` highlights, Ion Ink `#087F8C` actions and Chalk `#F4F8FC` workspace.
  Use The Godfather branding, compact section tabs and grouped ribbon commands,
  thin borders, dense tables and collapsible/resizable utility panels. Follow the
  supplied desktop application references; avoid oversized dashboard cards.
- Stack: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, consistent with `AGENTS.md`.
- A restrained, professional infrastructure-control-panel aesthetic. Neutral surfaces with limited semantic colors for healthy, degraded, offline, running, blocked, and failed states.
- Support dark and light themes; do not rely on color alone for meaning.
- Establish tokens for typography, spacing, radii, borders, elevations, semantic colors, and responsive breakpoints before expanding page designs.
- Use a shared component library for page headers, summary metrics, data tables, filters, status indicators, detail drawers, dialogs, toasts, empty states, skeletons, and audit timelines.
- No decorative graphs without actionable value. Prefer tables for precise operational data.
- Use Font Awesome 7 Free for icons then when needed.
- Configuration options for dashboard layout, colors, etc and the aforementioned, will be required for the two admins of the project. 

## Information architecture
### Global navigation
1. **Overview**: cluster health, capacity, active jobs, alerts, recent activity.
2. **Jobs**: submit, search, filter, inspect, cancel, retry, view attempts/checkpoints/artifacts.
3. **Nodes**: online/suspect/offline/draining/disabled, owner, OS, CPU/RAM/GPU/VRAM, models, policies, latency.
4. **Agents**: definitions, capabilities, model/tool requirements, versions, assigned policies.
5. **Models**: provider, deployment node, runtime, supported capabilities, memory requirements, observed latency.
6. **Workspaces**: private/shared tasks, artifacts, access boundaries.
7. **Integrations / MCP**: connections, scoped tools, approval policies, credential status (never secret values).
8. **Activity / Audit**: events, approvals, failovers, who did what and when.
9. **Settings**: user administration, node contributions, scheduler policies, alerts, system configuration.

Do not implement all screens in Phase 01. Establish a navigable shell only when authorized by the phase scope.

## Overview page
- Summary strip: online/total nodes, running/queued/blocked jobs, available model capacity, active alerts.
- Node health section with owner, location label (user-configured), platform, specialty, availability, and load.
- Job activity section showing owner/workspace, type, executing node, status, progress, and last update.
- Failover/activity timeline: node loss, lease expiration, reassignment, resume, and failure events.
- Clear links from summary cards to filtered detail views.
- Show timestamp and freshness of telemetry; distinguish unknown from zero.

## Node detail
- Identity: node ID, display name, owner, OS/architecture, worker version, last heartbeat.
- Capabilities: primary/secondary specialties, available models and runtimes, tool permissions.
- Hardware: CPU, RAM, GPU backend (CUDA/Metal/other/CPU), VRAM or unified-memory constraints, concurrency limits.
- Scheduling: dedicated/preferred/shared policy, drain/disable state, owner-controlled restrictions.
- History: assigned jobs, failures, availability events.
- Owner actions must respect backend permissions. Show explicit confirmation for drain/disable and warn about running work.

## Job detail and failover UX
- Show job ID, requester, workspace, priority, required capabilities, status, assigned node, and current attempt.
- Present chronological execution history: submitted -> assigned -> running -> checkpoint -> disconnected -> retry -> reassigned -> resumed -> completed.
- Distinguish 'resumed from checkpoint' from 'restarted from beginning'.
- Show last durable checkpoint and artifact references where available; do not promise recovery of unsaved local state.
- Cancel/retry actions must indicate expected effects and possible external side effects.
- Surface 'waiting for compatible node' and 'requires manual review' explicitly.

## Task submission
- Start simple: prompt, agent/workload selection, workspace, optional attachments/repository reference, priority.
- Advanced options (collapsed): model preference, allowed nodes, resource limits, timeout, approval requirements.
- Provide clear status and a direct path to the created job.
- Never imply an action executed merely because it was queued or approved.

## Multi-user and future contributors
- Both founding admins may manage shared platform configuration and workflows.
- Node ownership and local host restrictions remain independently controlled by each owner.
- Future contributors have explicitly granted capabilities and limited visibility by default.
- Private workspaces and secrets must not leak through dashboard lists, search, telemetry, notifications, or audit details.
- Show who owns a node and who requested a task without exposing private data unnecessarily.

## Responsive behavior
- Desktop: persistent sidebar, dense tables with sorting/filtering, split views or detail drawers.
- Tablet: collapsible navigation and simplified columns.
- Mobile: read-only overview and essential job status initially; do not force complex administrative tables into unusable cards.

## Interaction and feedback
- All long-running operations expose pending, success, failure, and cancellation states.
- Use confirmation dialogs for destructive/high-impact actions, and explicit approval workflows for production integrations.
- Never use optimistic UI to claim completion of a backend action before confirmation.
- Use sensible refresh intervals and event streaming where justified; indicate stale/offline data.
- Support filtering by owner, workspace, location, node, workload, and status.

## Required design deliverables
Before implementing a major screen, Codex should provide:
1. Purpose and target user actions.
2. Information hierarchy and navigation placement.
3. Component inventory and states (loading, empty, error, permission denied, offline).
4. Accessibility and responsive behavior.
5. API data dependencies and authorization boundaries.
6. A small acceptance-test checklist.

## MVP sequencing
- **Phase 01:** Design tokens and dashboard shell only if within approved Phase 01 scope; no invented live metrics.
- **Phase 03-04:** Backend node/job contracts; optionally mock interface sketches, not a full dashboard.
- **Phase 08:** Build operational screens with real backend data.
- **Phase 09:** Complete user/workspace administration and authorization UX, with minimum security controls in place before any remote exposure.
- **Later:** Visual agent workflow builder, richer reporting, configurable dashboards.

## Acceptance criteria
- A new user can tell which nodes are online, what work is running, and why a job is blocked or failing.
- An administrator can locate a failed job and inspect its failover history without reading raw logs.
- The interface correctly distinguishes unavailable telemetry, zero utilization, and stale measurements.
- Every privileged control is backed by server-side authorization.
- Keyboard-only navigation and core screen-reader workflows are supported.
- No production secrets or private workspace data appear in unauthorized views.

## Codex instructions
Read `AGENTS.md` and this document before UI/UX work. Follow the current approved phase. Propose the smallest useful design change, show relevant component states, implement only after authorization, run checks, report changed files and tests, and stop. Do not expand into future-phase functionality without approval.
