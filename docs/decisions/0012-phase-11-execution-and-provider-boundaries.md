# Phase 11: worker execution and independent provider credentials

Status: accepted for the explicitly authorized Phase 11 assignment.

Google OIDC authenticates a person and establishes an application session. Its
tokens and client secret are never inference credentials. Provider connections
belong to persistent user UUIDs, independently of Google identity subjects and
session lifetime. OpenAI and Anthropic API keys authorize separately billed API
use; consumer subscriptions and browser tokens are not supported credentials.

Provider secrets stay in the worker owner's operating-system credential store.
The coordinator receives only connection UUIDs, provider/model capabilities,
policies and usage. There is no server-side API-key upload or storage option.
Dashboard enrollment supplies a connection identifier and local setup instructions;
secret entry takes place on the worker. OS stores that are unavailable fail closed.

Paid execution requires explicit route/data-egress consent, an owner grant scoped
to submitter/workspace/model, and a durable invocation reservation. Private is the
default; platform administration grants no billing access. Unknown prices or usage
must never become zero-cost records. Uncertain external calls retain liabilities
for review; automatic paid retries and paid fallback are disabled initially.
Google logout revokes the application session, not the provider's API key. Provider
revocation blocks new invocations without changing Google login or node ownership.

Coding runs on opted-in workers in disposable workspaces with container isolation,
no network by default, no host credentials, and only owner-approved repositories
and commands. The coordinator stores artifacts and fences reports; it never runs
generated code. A completed patch and test report are reviewable artifacts. Git
push, deployment and destructive host operations are outside the coding tool set.
An interrupted coding command requires review rather than automatic replay.

## UI acceptance

Provider Connections is separate from Google account settings. It shows owner,
provider, worker availability, models, sharing, limits and estimated usage; keys
never appear. Empty, loading, revoked, unavailable and permission-denied states are
explicit. Existing workspace checks govern jobs and artifacts; owner-only checks
govern connection policy. All commands support keyboard access and narrow screens.

Job detail prioritizes the persisted answer, partial/completed status and downloads.
Raw payloads, checkpoints, attempts and event history live in Technical Details.
Release status comes from build metadata and the runtime environment.
