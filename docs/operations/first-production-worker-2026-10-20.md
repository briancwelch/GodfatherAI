# First production Windows worker - 2026-10-20

This sanitized operational summary records the previously authorized first-worker
onboarding and real inference validation. Personal identities, private addresses,
production record identifiers, exact network policy and production data are omitted.
Detailed evidence remains in private operator records, outside source control.

## Recorded validation

- The existing coordinator release and standalone Windows worker were used without
  rebuilding or replacing the deployed application.
- Worker archive and packaged-file checksums, native startup and actual hardware
  discovery passed. Discovery alone does not establish GPU execution or performance.
- The owner configured narrowly scoped private HTTPS connectivity with normal TLS
  verification. Public application DNS and application authorization were preserved.
- One individually owned machine credential was provisioned. Its secret was stored
  outside the repository under per-user Windows ACLs; PostgreSQL stores its digest.
  The existing standalone CLI does not use Windows Credential Manager or DPAPI.
- An authenticated owner submitted a real local-model inference job through the
  normal dashboard bridge. The initial token-limited request returned empty answer
  text; a subsequent request with a larger token allowance completed successfully.
  The owner confirmed the result and measured timing in the Command Center.
- Actual private-route authentication, public worker-route denial, blocked internal
  ports and loopback-only inference runtime checks passed.
- After confirming no active assignments, the worker was stopped and restarted.
  Health changed through suspect/offline/online; persistent node ownership and
  credential identity survived, process-session identity changed, and the completed
  result remained durable and unchanged.

## Operation and remaining limits

Start the previously configured worker from normal PowerShell:

```powershell
& "$env:LOCALAPPDATA\The Godfather\worker\start-worker.ps1"
```

It requires the owner's existing private network configuration and local inference
runtime. Configuration, credentials, logs and detailed validation records stay under
that private per-user installation and must not be published. No Windows service,
scheduled task or automatic login startup was installed. The worker remains an
unsigned candidate; the existing local runtime/model was reused without downloads.

These are historical, user-assisted production observations, not a new deployment
or a substitute for local regression tests. This report does not establish remote
macOS acceptance, active-job failover, full GPU offload or completion of Phase 10.
The later browser enrollment extension and macOS application require separate
production deployment and recipient acceptance.
