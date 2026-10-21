# ADR 0013: Activate explicit invitations through verified Google email

Status: accepted for the authorized onboarding repair.

## Problem

Invitation creation persisted an email-bound role grant and returned a secret
once as raw JSON. No delivery service existed, but neither the admin screen nor
the sign-in screen explained manual delivery clearly. An invited person who used
normal Google sign-in was rejected without the undistributed token.

## Decision

After the existing Authlib signature, issuer, audience, nonce, state, browser and
PKCE checks, a new identity can redeem exactly one active, unexpired, unused
invitation matching Google's verified email, case-insensitively. This creates a
new UUID bound to Google `sub`; it does not link or recover existing local users
by email. Existing linked users continue authenticating by subject, without role
changes from pending invitations.

Activation remains transactional and serialized, with row locking, single-use
consumption and auditing. Expired/revoked/used grants and ambiguous duplicate
pending grants fail closed. New duplicate pending invitations return an actionable
409 instead of silently selecting roles. Optional legacy tokens remain supported;
invalid supplied tokens are refused without email fallback.

The admin UI explicitly states that email is not sent and provides copyable
sign-in instructions for active invitations, including after refresh. Normal
sign-in needs no code. No SMTP service, Google permissions, Tailscale policy or
paid-provider credentials are introduced or changed.

## Consequences and validation

Possession of a separately delivered invitation secret is no longer required when
the verified Google email has one explicit administrator grant. Email verification
and the administrator's exact address selection therefore define initial admission;
Google `sub` remains the durable identity afterward. Invitation expiry and revocation
still control admission, and platform authority never changes node-owner consent.

Regression coverage includes code-free activation, role/identity preservation,
expiry/revocation/reuse, wrong/unverified email, ambiguous grants, duplicate creation,
legacy token compatibility, and invalid-code rejection. Browser acceptance exercises
normal second-administrator sign-in without a code; Google network responses are
mocked only in isolated tests. Real recipient acceptance remains a live user action.
