# ADR 0009: Source-free coordinator releases and separate workers

Status: accepted for local packaging only, 2026-10-20.

The first planned deployment targets one existing Ubuntu 24.04 AMD64 Droplet with
two vCPUs and 4GB RAM. The development environment on Windows/Docker Desktop/WSL2
must remain intact. Remote changes are not authorized by this decision.

Reuse the existing Dockerfiles and local Compose topology. Add an API production
stage with non-editable package installs and an explicit migration-directory path;
retain the local editable runtime/test stages. Reuse the dashboard's standalone
Next.js image. An allowlisted, versioned archive contains saved application and
dependency images, a standalone production Compose file, Caddy configuration,
empty environment template, checksums/image IDs and maintenance scripts. The
Droplet needs Docker/Compose and an operator environment, not Git or build tools.

Use fixed project/volume names across versions. Explicit maintenance quiesces the
API/scheduler before paired PostgreSQL/artifact backup and migration. Startup
requires exact schema readiness; failed migrations stop deployment. PostgreSQL
image changes require a separately reviewed upgrade. Rollback with schema changes
uses matching backups and reviewed new volumes; no automatic destructive downgrade.

Caddy publishes HTTPS while private networks hide databases and application ports.
Human browser requests use the existing same-origin bridge; worker routes on the
API hostname additionally require tailnet source addresses and existing machine
credentials. This requires approved split DNS and source-address acceptance on
the actual Linux host. Google OIDC, identity UUIDs, RBAC, node-owner consent and
lease fencing are unchanged. Environment secrets are protected operator files
visible to trusted root/Docker operators; they are never part of the archive.

Workers are a separate standalone product built natively per OS/architecture.
Native installers and short-lived single-use enrollment are a documented follow-on
prerequisite; reusable machine credentials are not relabeled as enrollment grants.
No inference runtime/model download or expanded host access is implied.

Consequences: larger portable archives and maintenance downtime, simpler server
installation, stable storage, explicit provenance and offline image loading.
Local tests cannot establish real Google, public TLS, tailnet, signing, physical
cross-platform or Droplet capacity acceptance. No Kubernetes/registry service,
external secret manager, automatic OS/service installation or public hosting is added.

Release provenance refinement: the coordinator builder requires clean committed
source and detects source/revision changes during building. Pin the six container
inputs by immutable SHA-256 in `infrastructure/release/images.lock.json`, passing
release build arguments while retaining existing development defaults. Record
these inputs and the exact commit in each release manifest. Application dependency
lockfiles remain authoritative; hash/version constraints additionally freeze the
isolated Hatchling build dependency closure without changing application versions.
This provides repeatable source/dependency inputs;
archive/build timestamps do not carry a byte-identical reproducibility guarantee.
