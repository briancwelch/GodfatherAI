# Optional coding project readiness

Accepted for the owner-requested worker recovery fix, 2026-10-23.

A saved coding project can outlive its Docker test image, local engine, Git
installation or folder access. Previously one unavailable dependency stopped the
entire worker before registration, behind a generic error. Carbon reproduced the
missing-image case after its 0.9.0-rc.1 update; excluding the project allowed
startup with cloud images still enabled. The owner subsequently confirmed that
an earlier requested cleanup removed the image; the update's restart exposed
that missing dependency. Installer code replaces application payloads and does
not manage Docker images.

Check owner-approved projects read-only, concurrently, within a 15-second
deadline at each Resume. Withhold unavailable projects from repository, coding
and Apply advertisements and execution configuration. Retain their saved IDs,
image pins, file scopes and permissions unchanged. If no project is ready, omit
the coding tool permission and coding/Apply runtimes. Other enabled capabilities
may register normally; malformed configuration and authentication still fail
closed. Existing scheduler compatibility, fencing and owner consent apply.

Report only project UUIDs and fixed diagnostic codes through worker events.
Resolve names, the saved image reference and recovery instructions locally in
Consigliere. Keep an attention panel visible through heartbeats and show each
affected project in Projects. Pause/Resume rechecks after repair, restoring the
same project identity and clearing the warning. Never download an image, change
Docker context, reset credentials, delete a grant or broaden permissions as an
automatic repair. Dependency loss during an active job still follows existing
bounded execution failures; this startup check is not continuous monitoring.

The Nodes EKG separately retains the actual heartbeat timestamps observed by its
mounted view in a bounded 60-second/64-entry history. New receipts append rather
than replace the trace, duplicate refreshes do not invent pulses, and offline or
stale traces dim and age out. This is view-local history, not a durable heartbeat
archive; no pulses are interpolated for missed polling intervals. Reduced motion
uses slower updates. No new API/schema or dependency is required.
