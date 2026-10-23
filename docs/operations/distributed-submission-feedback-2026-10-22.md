# Distributed job submission feedback

The owner reported that Run appeared to do nothing and offered no clear warning.
Read-only production inspection found zero distributed parents, distinguishing the
reported attempt from a submitted job waiting for workers. No live inference or
test jobs were started. BernieMac was offline with no advertised models or workflow
protocol at inspection; node-owner settings were not changed.

The form previously disabled Run for missing participants, agents or synthesis
support without a complete explanation beside the button. Native required-field
validation intercepted submission, and caught submission errors appeared only at
the top of the long page. Catalog refresh could clear that error. A missing overview
default also left the workspace value empty despite a usable workspace catalog.

The fix displays readiness blockers and offline/no-model warnings beside Run;
validates missing fields into a focused summary; retains server errors across
refresh; and shows pending and confirmed/queued states separately. Structured API
validation includes field locations and messages, excluding input/credential
values. Network failures and a 30-second confirmation timeout advise checking
history before retrying. No automatic POST retry is introduced. Existing backend
authorization, model matching, paid-use consent and worker permissions remain in
force. The first authorized workspace is a valid fallback.

Validation completed before release:

- Dashboard component/client regression suite: **32 passed**.
- ESLint, strict TypeScript, production Next.js build and diff whitespace checks
  passed.
- Isolated Edge acceptance passed empty-field errors, explicit old-worker synthesis
  blockers, permission rejection beside Run persisting after Refresh, structured
  validation without rejected-input echo, network failure guidance, default
  workspace submission, confirmed success, dependency graph, contribution bars,
  final results, cancellation, stale controls, dark theme and 390px layout.
- Screenshots and test receipt: `.cache/distributed-ui/`, including
  `submission-blockers.png`, `submission-rejected.png` and `result.json`.

This is a dashboard/client fix with no schema or worker changes. The coordinator
candidate is **0.6.0-rc.2**, retaining the verified **0.6.0-rc.1** worker downloads.
Production publication follows the existing owner authorization to deploy the
coordinator and synchronize GitHub. Public unauthenticated checks establish
deployment health and access controls; authenticated submission checks use an
isolated fixture rather than a real user session or billable provider.
