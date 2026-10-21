# Result previews and owner-approved actions

Accepted by the owner on 2026-10-21 within the Phase 11 usability milestone.
The owner authorized rebuilding workers when inspection established that the
existing builds could produce patches but could not safely apply them.

The Command Center presents accomplishments first: submitted task, persisted
summary, actual test-command results, changed files and per-file diffs. A completed
coding job means a patch was produced. Application is a separate operation, with
its own durable job, approval, worker receipt and confirmed outcome. Logs, attempts,
checkpoints, source hashes and command output use progressive disclosure.

`result.action` uses a versioned input/output contract, immutable source artifact
reference, explicit action kind, exact owned node and local target identity.
Workers advertise `result-actions-v1`, supported action kinds and individually
enabled project targets. Unknown versions/actions fail closed. Old workers never
receive these jobs and retain their existing inference/workflow protocol shape.
No coordinator-delivered scripts or executable plug-ins are installed or run.

The first action, `coding.patch.apply`, requires local `allow_apply` consent
(default false), the source job owner, node ownership, workspace access and the
exact reviewed artifact ID/checksum. The backend serializes approval under the
source row lock and rechecks grants at scheduling and execution. Application stays
on the original computer; a local side effect cannot safely migrate to a backup.
No schema migration is needed: PostgreSQL jobs, attempts and audit events hold
the durable action and invocation marker.

The worker independently verifies artifact integrity, approved paths, file types,
base commit and every affected file's contents, including edits hidden behind
Git index flags. Staged/unstaged edits in affected files and untracked/ignored
collisions block application. Unrelated edits and the staging index are preserved.
The worker keeps a local lock, source patch and receipt under Git metadata,
rechecks after one-time server authorization and uses Git's normal all-hunk
validation without `--reject`, `--3way`, hooks, commits, pushes or model commands.
Native line-ending conversion is explicit; `.gitattributes` remains authoritative.

Leases and worker health continue to renew. Interrupted or uncertain applications
are never automatically retried or reassigned. Lost replies require inspecting
the project and local receipt. Cancellation cannot undo an already started file
write. Editors do not honor the worker lock: pause editing affected files while
applying. Filesystem failures/crashes can leave uncertain effects; this is not a
claim of transactional or exactly-once filesystem behavior.

## Extension boundary

Presentation and execution are independent. Existing sanitized text, Markdown,
code, image/media, document downloads, tables and chart renderers are selected by
result content in the Command Center. New layouts, summaries, download controls
and compatible result envelopes can ship without rebuilding workers. Future
images, reports and analytics should return immutable artifacts plus descriptive
metadata and reuse the same preview/explicit-action lifecycle, rather than logs.

Adding a genuinely new local operation, model runtime or binary file writer still
requires a worker that implements and advertises that capability. This contract
avoids rebuilding for presentation changes; it does not promise that an old worker
can execute unknown capabilities. Generic artifact export primitives can be added
when Phase 12 defines actual output/destination permissions. No Phase 12 workload,
live paid inference or executable remote-update mechanism is introduced here.

## Screen design and acceptance

- Main action: inspect the accomplishment, expand file diffs, acknowledge review,
  then explicitly apply. The worker checks the project at execution time.
- Components: task/result header, compact workflow strip, verified facts, file
  disclosures, apply confirmation, outcome/blocked notice, evidence disclosure.
- Loading/unavailable/stale, running/partial, no changes, untested, tests failed,
  permission denied, worker upgrade/consent needed, queued, applied, blocked and
  uncertain completion each have explicit text. No invented metrics or test counts.
- Semantic buttons, labels and disclosures support keyboard use. Text accompanies
  diff colors. Long diffs scroll within the result; controls wrap on narrow screens
  and retain the existing theme tokens.
- Data comes from authorized job projections and integrity-checked artifacts.
  The browser cannot choose a host path, submit patch content, invoke worker APIs
  through its session bridge, or bypass local consent.
- Acceptance covers actual Git dirty-file/index preservation, conflicts, hidden
  edits, links, scope, authorization loss, artifact mismatch, duplicate approval,
  stale fencing, no replay, truthful result states and narrow-screen inspection.
