# Worker onboarding repair - 2026-10-22

The owner authorized repairing fresh Windows/macOS onboarding, incorporating the
existing version-reporting changes, rebuilding native workers, publishing them in
Command Center, and pushing the final changes to GitHub main.

## Behavior

The worker now paints its comparison code before opening the browser and selects
the Connection tab. A failed exchange keeps the previous code visibly marked
inactive, with instructions to close the approval page and start Connect again.
Certificate, DNS and timeout failures have specific, secret-free messages.
The previous flow cleared the code immediately after a polling failure.

Worker HTTPS retains system trust and adds a bundled Mozilla public-root store
from certifi. This dependency supplies public roots on fresh Windows installations
and standalone Mac Python builds; certificate and hostname verification remain
mandatory. Both packaging paths explicitly include the bundle. No trust bypass,
credential fallback, model download or host permission change is introduced.

The exact transport error on the recipient's fresh Windows computer was not
available. Source and an isolated frozen diagnostic on the developer's Windows
host both reached the expected unapproved HTTP 404. Missing system trust is covered
by a regression starting with an empty CA store, rather than asserted as a proven
recipient root cause.

The window title and footer show the embedded build version, or explicitly identify
an unreleased source checkout. Registration advertises that same build identity
through the previously implemented Command Center contract. A header badge shows
Disconnected, Awaiting approval, Connecting, Connected, Paused and recovery/refusal
states. Connected requires an actual registration/heartbeat acknowledgement.

## Verification and release

Local validation: 310 non-integration tests passed, four optional environment tests
skipped; Ruff and strict mypy passed. Windows native Tk/tray checks verified the code
before approval, automatic connection, acknowledgement-driven state, saved-session
restart, pause/resume, settings, projects and tray restoration. No private Google
account or actual recipient enrollment was used.

Frozen `--self-test` loads bundled trust and records the embedded version. With
`GODFATHER_SELF_TEST_ORIGIN` set, it sends a fresh, unapproved pairing exchange to
that origin and requires HTTP 404; it cannot save credentials or register a node.
The Mac release workflow enables this real-coordinator check for both native
architectures. Lost responses or secure-store failures remain non-replayable.

Native builds, artifact hashes, publication and final results are recorded below
after verification. Physical recipient installation/pairing and publisher signing
remain separate acceptance; Mac candidates use ad-hoc signing.
