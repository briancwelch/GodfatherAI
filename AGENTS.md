# AGENTS.md: The Godfather

## Mission
Build **The Godfather**, a private distributed multi-agent AI platform shared by two administrators in Las Vegas and Los Angeles. Both contribute independently owned worker computers with specialized capabilities: coding, images, analytics, reports, WordPress/WooCommerce MCP, research, and general AI. A centralized browser-based Command Center, planned for `app.the-godfather.ai` with an API at `api.the-godfather.ai`, manages agents, nodes, models, jobs, permissions, and recovery. The domain names are proposed deployment targets, not verified registrations. Nodes may disconnect; recoverable tasks must be reassigned to compatible available nodes.

This file governs Codex in VS Code. Follow it for every repository change.

Development is led by one developer. Both founding members are platform administrators; the second administrator is not a second developer.

## Mandatory rules
1. Implement **one phase at a time**. Test, document, report results, and stop. Do not advance without explicit direction.
2. Prefer the simplest working architecture: modular-monolith control plane plus independent workers. No Kubernetes, service mesh, distributed database, or speculative microservices.
3. Never deploy, modify external systems, access private accounts, install services, or perform destructive operations without explicit authorization for that action. A project discussion is not execution approval.
4. Both users administer shared services, but neither automatically gains access to the other's host, private workspace, credentials, repositories, or files.
5. PostgreSQL is authoritative for jobs, assignments, attempts, checkpoints, and events. Redis may signal work but must never be the only durable job store.
6. Agent definitions are portable; do not hardcode agents to machines. Nodes advertise primary and secondary capabilities and resource limits.
7. Failover resumes from **durable checkpoints**, not lost GPU state or unsaved work. External side effects are not assumed exactly-once.
8. Prototype on existing hardware and simulated workers. Do not make new hardware a prerequisite.
9. Keep AI providers interchangeable through a model gateway; start with Ollama and OpenAI-compatible APIs.
10. Never claim tests passed unless actually executed. Report limitations and failures plainly.
11. Workers must support Windows, macOS (Apple Silicon and Intel where feasible), and Linux without requiring a single GPU vendor or OS. Detect actual capabilities; do not assume parity across hosts.
12. The Command Center is a browser-based, OS-independent application. Both founding users are equal platform administrators; future contributors have limited roles by default. Platform administration never overrides a node owner's host-level restrictions.
13. Treat `app.the-godfather.ai` and `api.the-godfather.ai` as planned public-facing names. Do not register domains, change DNS, deploy publicly, or expose services without explicit authorization.
14. Design the coordinator for an independent, always-on Linux VPS; develop locally first. Never require either contributor's desktop to host the control plane.
15. Keep checkpoints, artifacts, execution requirements, and agent definitions portable. A job may migrate only to a node that satisfies its OS, architecture, runtime, dependency, model, and tool requirements.
16. For any frontend, dashboard, or UX/UI implementation, read and follow docs/design/UI-UX.md. AGENTS.md remains authoritative for architecture, security, and implementation phases. Do not introduce dashboard features outside the currently authorized phase.
17. The Godfather must support an extensible number of users, worker nodes, and geographic locations. Never hardcode the initial two administrators, four example nodes, or Las Vegas/Los Angeles locations into application logic. All users and nodes must be dynamically managed through persistent identities, ownership relationships, permissions, and capability-based scheduling. Future contributors must be able to join or leave without requiring application code changes or orchestrator restarts.
18. After completing a phase and before moving onto the next one, commit and push to Github repo, so each phase is saved.


## Architecture
```text
Browser clients: Vegas admin / LA admin / future contributors
                           |
         app.the-godfather.ai (Next.js Command Center)
                           |
          api.the-godfather.ai (FastAPI control plane)
                           |
       Independent Linux VPS (planned production host)
          /                |                 \
  PostgreSQL          Scheduler/API         Redis
   (durable)          + audit/auth       (notifications)
                           |
         Authenticated outbound worker connections
                (private Tailscale network)
          /                |                  \
  LV Windows nodes     LA macOS nodes     Future Linux nodes
  coding / images     analytics/reports   any allowed capability
                           |
       Portable agents / model gateway / scoped MCP tools
```
The VPS is the initial production target, not a prerequisite for local development. The Command Center may be accessible through HTTPS, but internal databases, inference endpoints, and worker administration are never public. Worker connections initiate outbound from contributor devices. Tailscale provides private connectivity; application authentication and authorization remain mandatory. Node roles are preferences, not permanent bindings. Coordinator high availability is a later enhancement.

The Godfather must support hybrid local and frontier AI inference using Bring Your Own API Key (BYOK). Each node owner may configure provider-specific credentials for OpenAI, Anthropic, Google Gemini, or other supported APIs. Credentials must remain under the owner's control, preferably stored securely on the worker node, and must never be exposed to other users, logs, or the central scheduler. The node advertises permitted model capabilities, not secrets. Implement provider-neutral routing with native adapters where necessary, credential-sharing policies (private, approval-required, budget-limited), per-owner and per-job cost tracking, explicit authorization for cross-user paid inference, and configurable spending limits. Never silently switch from free local inference to billable cloud inference. Preserve cross-platform support, portable agent execution, existing lease/fencing protections, and failover safety. Treat application spending limits as safeguards rather than guaranteed billing caps. Design this as an extension of the existing model gateway, not a separate orchestration system.

BYOK implementation was separately authorized in the user's Phase 11 assignment. Keep Google Sign-In independent of frontier API credentials and paid-use permissions. See `docs/operations/phase-11.md` and `docs/architecture/byok-plan.md`. Live billable calls still require separately supplied credentials and explicit spending authorization; historical Phase 06/07 boundaries remain unchanged.

## Stack
- **Editor / source:** VS Code, Codex, Git, GitHub.
- **Frontend:** Next.js, React, strict TypeScript, Tailwind CSS, shadcn/ui.
- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic.
- **Tooling:** uv, Ruff, pytest, ESLint, strict TypeScript, GitHub Actions.
- **Persistence:** PostgreSQL; Redis for wakeups and transient coordination.
- **Workers:** Installable Python worker supporting Windows 11, current supported macOS (Apple Silicon and Intel where feasible), and mainstream Linux distributions including Ubuntu; OS-specific installation/service management is isolated behind adapters.
- **AI:** Ollama, provider-neutral OpenAI-compatible model interface; detect CUDA, Apple Metal, supported AMD backends, and CPU-only operation without assuming equal performance or model availability.
- **Agents:** LangGraph when stateful multi-step workflows justify it.
- **Integrations:** MCP gateway with scoped permissions and approval gates.
- **Networking:** Tailscale plus application-level authentication.
- **Deployment:** Docker Compose for local coordinator dependencies and an independent Linux VPS in production; native or suitable packaged workers for Windows/macOS/Linux.
- **Monitoring:** Structured logs initially; Prometheus/Grafana later.

## Target repository structure
```text
the-godfather/
├── apps/
│   ├── dashboard/
│   └── api/
├── packages/
│   ├── worker/
│   ├── agent-runtime/
│   ├── model-gateway/
│   ├── shared-schemas/
│   └── mcp-gateway/
├── infrastructure/
│   ├── docker/
│   ├── migrations/
│   ├── monitoring/
│   └── tailscale/
├── tests/
│   ├── integration/
│   ├── e2e/
│   └── fault-injection/
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── protocols/
│   ├── security/
│   └── operations/
├── scripts/
├── AGENTS.md
├── .env.example
├── compose.yaml
├── README.md
└── pyproject.toml
```
Create components when their milestone needs them, not empty abstractions for future features.

## Centralized web administration and tenancy
- Build one responsive, browser-accessible Command Center; the proposed deployment endpoints are `app.the-godfather.ai` and `api.the-godfather.ai`. Reserve the apex domain `the-godfather.ai` for a redirect or landing page if desired. Domain ownership, DNS, TLS certificates, hosting provider, and public availability require separate decisions and explicit authorization.
- Both founding members have equal **platform administrator** roles. Future roles include **contributor** (manage owned nodes and permitted jobs) and **member** (use authorized agents/workspaces). Roles are application-level, not machine administrator privileges.
- Separate platform-wide configuration from node-owner consent. Even a platform administrator cannot access another owner's files, secrets, repositories, or shell unless that owner explicitly exposes an approved capability.
- The dashboard must support authenticated user sessions, node onboarding/revocation, node ownership, live health, job history, agent/model configuration, contribution policies, audit events, and workspace-scoped views.
- Establish a minimal dashboard shell and secure login foundation early; full dashboard functionality remains Phase 08. Do not publish an unauthenticated prototype on the internet.

## Cross-platform worker and execution contract
- Use portable Python code for core worker behavior. Isolate OS-specific operations (Windows services, macOS launchd, Linux systemd, process spawning, paths, shells, hardware discovery, and sandboxing) behind tested adapters.
- Workers advertise OS and version, CPU architecture, available accelerators and supported backends (CUDA/Metal/AMD/CPU), resource capacity, installed model runtimes, toolchains, and supported sandbox/container execution modes. Never require CUDA on macOS or assume Docker provides identical GPU access on every host.
- Jobs declare platform constraints (`any`, Windows, macOS, Linux), architecture, dependencies, tool permissions, model requirements, and artifact/workspace requirements. Scheduler must reject incompatible failover destinations and queue or pause safely when none exists.
- Use versioned, durable, centrally accessible artifact/checkpoint references; never depend on unreplicated local files. Coding tasks use version-controlled workspaces and portable patches/commits where possible. Windows-specific build/test tasks cannot be assumed runnable on macOS or Linux.
- Test core worker functionality on Windows, macOS, and Linux in CI where practical; perform actual inference and GPU tests on available physical hardware. Mark untested backends clearly.

## Node and scheduling model
Nodes authenticate individually and advertise node ID, owner, OS/version, CPU architecture, protocol version, capabilities, primary/secondary specialties, installed models, accelerator/backend type, CPU, RAM, GPU/VRAM or unified memory where applicable, current load, concurrency limit, and scheduling policy (`dedicated`, `preferred`, `shared`). Workers connect outward to the coordinator; no public inbound home-network ports. Use configurable heartbeats, initially every 10 seconds, and an initial 30-second offline threshold after missed heartbeats. Distinguish `online`, `suspect`, `offline`, `draining`, and `disabled`.

Jobs require ID, owner, workspace, type, input/artifact references, capabilities, resource constraints, priority, timeout, cancellation, retry policy, status, attempt, lease/fencing token, and checkpoint. States: `PENDING`, `ASSIGNED`, `RUNNING`, `RETRY_WAIT`, `COMPLETED`, `FAILED`, `CANCELLED`. Queue work when no compatible node exists.

Use transactional PostgreSQL claims (e.g. `FOR UPDATE SKIP LOCKED`), lease expiration, monotonically increasing fencing tokens, and attempt records. A stale worker must not commit results after reassignment. Enforce permissions, OS/architecture/runtime compatibility, model availability, resource limits, node owner policy, concurrency, and fairness. Prefer primary nodes and allow compatible backups. Use at-least-once attempts; side-effecting operations require idempotency keys, reconciliation, or explicit approval.

**Canonical failover test:** LA user submits portable coding job -> LV Windows coding node accepts -> LV node disconnects -> lease expires -> coordinator fences stale attempt -> compatible LA macOS node accepts -> resumes from durable checkpoint and replicated/versioned workspace artifacts. Never promise recovery of unsaved local files, GPU state, or interrupted external side effects. Coding tasks should use isolated worktrees and reviewable commits/patches; other tasks use durable artifact references. If recovery is unsafe, pause for review.

## Security and permissions
Both founding users may administer the shared Command Center, agents, scheduling, and jobs; future contributors receive explicitly scoped roles. Node owners independently control resource contributions, host permissions, local paths, and tool exposure. Workspaces are private by default and shareable explicitly. Enforce authorization on the backend, not only in UI. Tailscale network membership is not authentication; use worker credentials and authenticated sessions. Scope MCP tokens to user/workspace/tool and execute sensitive tools only on authorized nodes. Never expose Ollama, Redis, PostgreSQL, or worker admin APIs publicly. Redact secrets from logs, prompts, and artifacts. Production WordPress writes, deployments, deletions, and other high-impact actions require explicit approval. Before remote deployment or real data use, implement minimum API/worker authentication even if full multi-user RBAC is a later phase.

## Command Center requirements
0. Web delivery: browser-based responsive UI at planned `app.the-godfather.ai`, authenticated API at planned `api.the-godfather.ai`, with HTTPS and server-side authorization before internet exposure.
1. Overview: online/offline nodes, agents, running/queued jobs, events.
2. Nodes: owner, health, OS, CPU/GPU/RAM/VRAM, models, capabilities, latency, policies, drain/disable.
3. Jobs: submit, inspect, prioritize, cancel, retry, checkpoints, attempts, artifacts, failover history.
4. Agents: definitions, model requirements, tools, policies, assignments, workflows.
5. Models: providers, deployments, resource needs, compatibility, performance.
6. MCP: connections, scoped tools, approvals, auditing, secret-safe configuration.
7. Users/workspaces: identities, permissions, private/shared assets, quotas.
8. Events/audit: who initiated and approved actions, executing node, outcomes.
9. Settings: scheduler, health thresholds, contributions, backups.
A visual workflow builder is a later feature, not MVP scope. Never display invented live metrics outside an explicitly labeled demo mode.

## Implementation roadmap: mandatory sequence

### Phase 01: Repository and environment
Initialize monorepo, uv/Python and Next.js/TypeScript, formatting/lint/type checking, pytest, `.env.example`, `.gitignore`, local PostgreSQL/Redis Compose, CI, and Windows/macOS/Linux setup docs. Add a minimal dashboard shell, cross-platform compatibility policy, and local-only development configuration (no public deployment). **Gate:** The developer can clone, install, run dependencies, and pass checks using repeatable Windows/macOS/Linux setup instructions. There is no second-developer acceptance requirement; both founding users remain equal platform administrators. No application features. The entire Godfather control plane must run locally on Windows using Docker Desktop with WSL2. All worker registration, scheduling, checkpointing, failover, and dashboard functionality must be testable using multiple simulated worker processes on one physical machine. Production deployment to an Ubuntu-based DigitalOcean Droplet must use the same containerized architecture with environment-specific configuration. No cloud resources are required during initial development. Provide local URL for testing.

### Phase 02: Control-plane API
FastAPI `/api/v1`, `/health/live`, `/health/ready`, config validation, structured logs, correlation IDs, SQLAlchemy/Alembic. Schema for users, workspaces, nodes, capabilities, models, agents, jobs, attempts, checkpoints, events, ownership. **Gate:** Migrations and API/database integration tests pass after restart.

### Phase 03: Worker registration and health
Authenticated registration, versioned contracts, OS/architecture/GPU-backend resource discovery, outbound connection, heartbeats, health transitions, simulated workers, and Windows/macOS/Linux adapter tests. **Gate:** Two workers register; stopping one marks it offline without affecting the other; cross-platform core worker tests pass on supported OS runners.

### Phase 04: Durable scheduler
State machine, job submission, transactional claims, leases/fencing, retries, cancellation, resource matching, preferred/backup nodes, fair scheduling, persistent events. **Gate:** 100 synthetic jobs across two simulated workers finish in valid states with no conflicting assignment; pending work survives API restart.

### Phase 05: Local model inference
Provider-neutral model gateway, Ollama and OpenAI-compatible adapters, discovery, streaming, timeout/cancellation, token/latency metrics. **Gate:** Submit a job and stream a real local model response through the API.

### Phase 06: Agent runtime
Versioned agents, allowed tools, durable workflow state, checkpoint serialization, artifact references, LangGraph if warranted. Start with read-only multi-step workflow. **Gate:** Restart a process mid-workflow and resume from checkpoint.

### Phase 07: Automatic failover
Lease expiry, stale-attempt fencing, backup matching, checkpoint restoration, safe retries, fault-injection. **Gate:** A portable synthetic coding job transfers from a simulated Windows LV worker to a compatible macOS LA worker without losing committed steps or duplicating protected side effects; an OS-specific incompatible job remains safely queued.

### Phase 08: Web Command Center
Complete the Next.js dashboard foundation from Phase 01: overview, nodes, jobs, agents, models, events, live status, cancellation and retries. **Gate:** Observe a simulated worker failure and reassignment in UI using real backend state.

### Phase 09: Full authentication and authorization
Harden the early authentication foundation for two equal founding administrator accounts; add contributor/member roles, workspace isolation, RBAC, node-owner restrictions, tool approvals, and audit logs. **Gate:** Cross-user authorization tests pass; platform admin cannot bypass node-owner restrictions.

### Phase 10: Vegas-to-LA deployment
Tailscale network, least-privilege grants, independent Linux VPS coordinator, planned HTTPS hostnames and TLS, worker onboarding/revocation, one Windows worker in Las Vegas and one macOS worker in Los Angeles; no public exposure before security gates pass. **Gate:** Authorized admins can use the HTTPS Command Center; a remote macOS worker executes a synthetic task and compatible failover works after disconnection.

### Phase 11: Coding and WordPress agents
Coding agent with isolated worktrees, Git checkpoints, test runs, reviewable diffs; WordPress MCP read-only diagnostics first, then approval-gated writes. **Gate:** Coding produces a reviewable patch/test report; WordPress read-only task respects credentials and scopes.

### Phase 12: Images, analytics, reports
Image model adapter and GPU scheduling; restricted SQL/Python analysis, reproducible reports, durable artifacts. **Gate:** Each workload uses preferred node and a compatible backup when available.

### Phase 13: Resilience and observability
Metrics/traces, alerts, backup/restore, quotas, rate limits, chaos tests for node/network/coordinator failure and stale attempts. **Gate:** Recovery behavior is measured and runbooks are verified.

### Phase 14: Production hardening
Security review, dependency scans, secret handling, version compatibility, upgrades/rollback, incident response, deployment docs, owner onboarding/offboarding. **Gate:** Both admins can operate the platform from documentation.

## Implementation quality standards
- Write typed, modular, testable code. Validate external inputs. Keep API contracts versioned.
- Add unit tests for domain logic, integration tests for persistence, and fault-injection tests for recovery.
- Avoid `sleep`-based flaky tests where fake clocks or deterministic event triggers suffice.
- Use UTC timestamps in storage; display local time in the UI.
- Use migrations for schema changes. Never silently destroy data.
- Do not commit secrets, API keys, customer data, `.env` files, or real credentials.
- Never run untrusted generated code or SQL on the coordinator host. Use isolated, restricted execution environments with explicit filesystem/network scopes.
- Prefer observable failures over silent retries. Set bounded retries and dead-letter/failure states.
- Every new feature needs tests, docs, and meaningful errors. Every new dependency needs justification.
- Preserve backward compatibility of worker protocols or provide documented migration paths.
- Keep infrastructure and hardware requirements proportional to measured needs.

## Codex workflow for every task
1. Read this `AGENTS.md`, `README.md`, the current milestone, relevant architecture docs, and existing code.
2. Summarize the requested scope and propose the smallest implementation plan. State assumptions and security impact.
3. Implement only the authorized milestone; do not refactor unrelated modules or introduce future features.
4. Run relevant formatting, lint, type checks, unit tests, and integration tests where possible.
5. Update docs, tests, and an ADR if the architectural decision changes.
6. Report: files changed, behavior implemented, tests actually run/results, unresolved issues, security concerns, and next recommended milestone.
7. **Stop and wait for explicit approval** before proceeding to the next milestone or taking external actions.

## Scope and deployment safeguards
- `the-godfather.ai` is a proposed product domain, not evidence of ownership or DNS readiness.
- Phase 01 may scaffold the dashboard and local development environment, but must not deploy services, purchase hosting, register domains, change DNS, or connect real production credentials.
- Before any public deployment, require TLS, session authentication, API authorization, worker credentials, rate limiting, secret storage, audit logging, and backup/restore verification.
- Onboarding a future contributor must require an explicit invitation and per-node permission grants. Leaving the cluster must revoke credentials without deleting the owner's local data.

## First assignment
Start with **Phase 01 only**. Establish the repository and repeatable Windows/macOS/Linux development environment, including a nonfunctional local dashboard shell. Do not implement job scheduling, worker runtime features, agent workflows, functional dashboard management features, public hosting, or live external integrations until their phases are authorized.
