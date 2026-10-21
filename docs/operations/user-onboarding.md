# User onboarding

Tailscale access, The Godfather account access and paid-provider credentials are
separate. A Tailscale invitation does not create a Godfather user.
For the new [tray worker](simple-onboarding.md), authenticated HTTPS is the normal
transport and Tailscale is optional once the coordinator candidate is activated.

## Administrator

1. Open Account / Administration and create an invitation for the person's exact
   Google account email and intended roles. Use `platform_admin` only when equal
   platform administration is intended.
2. No email is sent automatically. Select **Copy sign-in instructions** on the
   active invitation row and share those instructions privately.
3. The row remains available after refresh. Expired, used and revoked invitations
   cannot activate a new account. An existing active invitation must be revoked
   before creating a replacement for that email.

Do not create a local account or extract Google tokens for normal onboarding.
Creating an invitation preauthorizes access; the user record is created only after
the recipient completes Google verification and accepts it.

## Recipient

Open the Command Center and select **Continue with Google**. Choose the exact
invited Google email before the invitation expires. No invitation code is needed.
Legacy codes can still be entered in the optional invitation-code disclosure.

Successful activation consumes the invitation and binds the new user UUID to the
verified Google subject. Later sign-ins use that identity. Initial platform roles
come from the invitation; workspace memberships and node permissions remain explicit.

## Troubleshooting

- **Godfather says sign-in was not authorized:** check the Google email actually
  selected, invitation expiry/revocation/use and whether more than one historical
  pending invitation exists. Revoke obsolete duplicates. An invalid legacy code
  is refused even if the email has a valid invitation; omit it for normal sign-in.
- **Google blocks access before returning:** the Google OAuth audience/testing
  settings may need the invited address approved as a test user. The app cannot
  override Google's denial. Google Cloud changes require their own authorization.
- **Existing unlinked local identity:** use the established explicit offline
  identity-linking procedure. Matching email never transfers its ownership/history.
- **No email received:** email delivery is manual. Share the application URL and
  exact invited email; no mailed code is required.

The application never sends messages to recipients automatically and does not
introduce an SMTP service. Real recipient acceptance must be checked with that
person; mocked Google test responses are only automated regression evidence.
