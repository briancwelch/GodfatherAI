# Account API connections and local project setup

Accepted for implementation by the owner, 2026-10-21, within Phase 11 usability.
Candidate activation is separate.

Account settings accepts an OpenAI/Anthropic key and explicitly selected owned
computers. A model-list request to a fixed official HTTPS API tests authentication
without inference. AES-256-GCM uses random nonces and owner/provider associated
data. The operator vault key stays in private environment configuration, outside
PostgreSQL and release archives. Saved keys never return to browsers. Only
individually selected owned workers with local opt-in and a matching authenticated
session may retrieve them; workers hold plaintext only in memory. Scheduler, job
and artifact records contain references/capabilities, never keys.

Encryption at rest does not protect against a compromised trusted API process or
an operator possessing both database and vault key. Keep backups confidential and
separate. Preserve the vault key across upgrades/restores. Rotation/loss requires
a reviewed migration or owners re-entering their provider keys. Google sessions,
machine credentials and local project grants remain separate.

Account connections are private. Providers handle billing and spending limits;
Godfather requires no prices, budgets or billing reconciliation. Usage is
informational. Durable invocation markers prevent duplicate replay of uncertain
external calls. Paid-model selection and visible data-egress confirmation remain.
No paid fallback/retry is introduced. Historical local-credential APIs and usage
remain compatible; the old billing-management UI is removed.

The tray app's Coding projects dialog selects a folder, named workspace, existing
Docker image, committed file scope and literal test command. Read-only checks
validate Git/image prerequisites. Resume enables the existing workflow/coding
runtime and repository advertisements. Only the connected owner receives project
access. Existing sandbox restrictions, patches, fencing and file exclusions remain.
No project edits or tool/image/model downloads occur automatically.

Main, project and advanced windows share bounded scrollable content with wrapping.
Show worker is the default tray activation action. Native smoke checks cover
dispatch, resizing, project add/remove and lifecycle. Physical recipient behavior
is separate acceptance. Tests also cover cross-owner denial, missing vault key,
unselected/non-opted-in computers, encryption binding, disconnect, secret-safe
metadata/logs/serialization, and provider billing without price/budget gates.
