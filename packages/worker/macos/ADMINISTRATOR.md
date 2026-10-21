# Mac worker administration

Invite the exact Google account with the contributor permission. Share the
Command Center address and the installer from Nodes / Connect a computer.
Invitations do not send email automatically. Browser approval binds the machine
to the signed-in owner; the app stores its credential in that owner's Keychain.
Do not create or copy a reusable credential file for normal desktop onboarding.

Activate the reviewed coordinator candidate with its authenticated HTTPS worker
routes before asking recipients to connect. Tailscale is optional. Only worker
operations are exposed; the dashboard retains session/CSRF checks and node-owner
restrictions. Private databases, Ollama and host administration remain private.

Native ARM64 and Intel build jobs prepare separate app/DMG candidates. The current
publisher has no Developer ID signing/notarization credentials, so these candidates
are unsuitable for claiming ordinary Gatekeeper-approved worldwide installation.
For a distribution release, use an Apple Developer ID Application certificate and
notarization Keychain profile with the existing build options. Keep signing secrets
out of the repository and contributor devices.

See `docs/operations/simple-onboarding.md` for exact build/staging commands,
operator setup, acceptance boundaries and production activation status.
