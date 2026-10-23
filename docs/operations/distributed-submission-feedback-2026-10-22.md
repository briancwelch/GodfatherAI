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

## Activation evidence

Coordinator **0.6.0-rc.2** was activated from clean source
`217f497e6d1f4ad25b5619fb837b5cf68417a058`, pushed to `origin/main`.
Archive SHA-256:
`607a09f594989f9eb87e6ccf9a851409d354dc303e69ed0000ad61578e6eaff3`.
All ten disposable release gates passed, including image identity/content,
migrations, private services, proxy/anonymous denial, six installer download hashes,
actual database/artifact restore and restart persistence.
Receipt: `.cache/release-tests/049cc83b99d3/result.json`.

All five production services are healthy on the exact new images/revision. Only
Caddy publishes host ports. Migration remains `0016_distributed_jobs`; the production
environment is byte-identical and mode 600. Stable fingerprints matched all existing
records: 2 users, 2 Google identities, 3 workspaces, 1 membership, 6 credentials,
4 node ownership/policy records, 12 jobs, 7 agents, 6 artifacts, 3 checkpoints,
4 provider connections and 1 encrypted account key. No inference or distributed
job was created by verification. Live backup checksums, PostgreSQL dump listing
and artifact gzip integrity passed for
`/opt/the-godfather/state/backups/20261023T001620-1383729`.

Server evidence:
`/opt/the-godfather/state/deployments/distributed-feedback-20261023-rc2`.
Local transport/public evidence: `.cache/distributed-feedback-0.6.0-rc.2/`.
The initial slow SFTP staging transfer was replaced by quiet SCP; the completed
archive matched its trusted hash before extraction and activation. No running
service was changed by that transfer retry.

The public HTTPS feedback JavaScript was downloaded and matched the deployed
container's exact SHA-256. It includes the missing-requirements, failed-submission
and timeout messages. Receipt:
`.cache/distributed-feedback-0.6.0-rc.2/public-feedback-bundle.json`. This verifies
delivery of the fix without impersonating a customer account; interactive failure
and success behavior was verified in the isolated browser acceptance above.

All **68 public HTTPS checks passed** after activation. Authentication and origin
boundaries, private API denial, both runtime catalogs and all three existing worker
installers on both hostnames passed, including six complete download hashes.
Receipt: `.cache/distributed-feedback-0.6.0-rc.2/public-result.json`.
No serious unresolved release errors remain. Live authenticated multi-node
inference and billable provider calls were not executed; they are separate from
the isolated submission acceptance and production delivery verification.
