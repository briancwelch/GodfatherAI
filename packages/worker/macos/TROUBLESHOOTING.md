# Mac worker troubleshooting

- **macOS blocks the app:** the current candidate is not Developer ID signed or
  notarized. Ask the administrator for a signed distribution build. Signing needs
  the publisher's Apple Developer credentials, not your Google account.
- **Cannot connect securely:** check the Command Center address and internet.
  This candidate uses authenticated HTTPS. Do not edit hosts files or add
  Tailscale grants as part of normal setup. The coordinator must first activate
  the matching HTTPS worker release.
- **No approval appears:** use Connect in the app, sign in with the exact invited
  Google account and approve the matching code. The app detects approval itself.
  Cancel and reconnect if its five-minute pairing window expires.
- **Connection refused:** ask the administrator to check account permissions,
  node state and credential revocation. A Tailscale account is not authorization.
- **Keychain unavailable:** unlock your login Keychain. The app never falls back
  to a plaintext credential file. A failed/ambiguous exchange requires new pairing;
  revoke an unused credential in Command Center if necessary.
- **No AI models:** enable only already-installed local models. No model runtime
  or model download is performed. A connected node with local AI off reports
  availability but does not execute AI inference.
- **Previous worker session:** quit the old worker. The coordinator waits for its
  lease to expire safely before accepting a replacement session.

Existing private Mac enrollments retain their original API endpoint until the
owner explicitly replaces them. The new tray source does not change the running
coordinator or another person's device by itself.
