# ADR 0033: Contribution capacity and explicit model admission profiles

- Status: Accepted for order #6, finding #10
- Date: 2026-10-25

Keep `Resources.cpu_count`, RAM and GPUs as the worker's scheduling capacity.
Desktop contribution limits remain capped against current discovery; unknown RAM
remains unknown and ordinary GPUs remain withheld. Add optional `hardware`
measurements for presentation only. Neither scheduler matching nor reservations
may use those measurements to increase a contribution. Managed shared engines
retain their separately consented GPU advertisement and exclusivity checks.

Older workers omit the optional measurements and remain accepted; omission is
serialized with the legacy resource shape. The UI labels older reports as
scheduling capacity and marks separate physical totals unavailable. Deploy the new
coordinator before distributing new workers. Older strict coordinators do not
understand the added telemetry: an image-only downgrade requires compatibility
review or a paired restore, even with the same Alembic head. Worker protocol
versions, credential/session checks, leases and checkpoint contracts stay unchanged.

Populate existing deployment `estimated_ram_bytes`/`estimated_vram_bytes` from
explicit owner-local profiles, never from model/download bytes. Profiles require
positive host RAM, explicit GPU memory (zero means CPU-only), a bounded context and
an evidence note. Optional digest binding withdraws a changed model until its
profile is reviewed. Profiles are configured estimates, not measured live telemetry.
Ollama requests use the profile's context and disable GPU offload for CPU-only
profiles. OpenAI-compatible profiles attest the owner's matching server configuration.
Unprofiled memory remains unknown; explicit job requirements continue to fail
closed on unknown available capacity. No guessed default model sizes or automatic
model loading, download or benchmarking is introduced.

Existing PostgreSQL-backed reservations, concurrency, freshness, workspace and
owner policy matching remain authoritative. Recovery rechecks current capacity;
an incompatible destination stays queued with its committed checkpoint preserved.
