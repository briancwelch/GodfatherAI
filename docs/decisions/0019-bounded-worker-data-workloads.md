# 0019: bounded worker data and image stages

Status: owner-authorized Phase 12, 2026-10-21.

Extend the existing sequential agent runtime with analytics, report and local-image
stage kinds. Deterministic workloads do not require a text-model deployment.
Versioned input/output contracts, immutable artifacts, existing checkpoint prefixes
and scheduler resource/ownership policies remain the execution boundary.

Use fixed Python standard-library calculations in the existing local Docker
isolation pattern. The 1 MiB dataset limit makes a new scientific-runtime dependency
unnecessary for this increment. No coordinator execution, generated code or live
SQL runs. Excel support is intentionally limited to bounded, values-only first-sheet
workbooks. HTML/Markdown/CSV/Excel report output avoids a new PDF renderer dependency.

Use an independent image-provider protocol in the existing gateway; the first
adapter targets an explicitly configured installed loopback AUTOMATIC1111 backend.
No cloud adapter can bypass account/BYOK authorization. No model weights, image
backend, Docker image, local service or paid call is installed/executed implicitly.

Raise immutable JSON artifact envelopes from 256 KiB to 8 MiB with an additive
constraint migration, per-download integrity validation and bounded transport.
Uploads remain durable in PostgreSQL job inputs. Node-owner opt-in and workspace
membership remain independent of platform administration. Report recovery consumes
the committed analytics artifact and cannot replace its structured calculations.

The owner confirmed there is no authorized real dataset. Deploy usable upload and
download interfaces, retain honest unavailable states and reserve live acceptance
for actual owner-submitted data. Google Drive/Sheets requires a separate data
connection; existing identity login consent must never become file-access consent.
