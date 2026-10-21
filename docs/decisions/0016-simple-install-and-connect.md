# Simple installation and outbound HTTPS

Status: accepted for implementation by the owner, 2026-10-21. Production activation is separate.

The normal worker is a desktop tray app. Open it, enter the Command Center address,
click Connect, and approve the matching code in the browser using an invited Google
account. Approval automatically starts the saved worker. Later launches reconnect.
Pause, resume, settings, Command Center and quit are available from the tray.

The main window shows connection status, address and local-model consent. Hardware,
capacity and explicit sharing scopes are advanced settings. Loading, awaiting approval,
connecting, connected, retrying, paused, refused and expired are distinct states.
Controls have text labels and keyboard access; status never depends on color alone.
Closing the window hides it only when the tray is available. Quit stops the worker.

Workers use the same configured HTTPS origin as the browser. Tailscale is optional.
Only worker routes cross the reverse proxy; application authentication, ownership,
leases, fencing and contribution policies remain enforced by the existing API.
Google identity and paid provider credentials remain separate. Saved machine secrets
are bound to their coordinator origin and stored in the operating system credential
store. No model downloads or host-file, DNS or firewall edits occur during onboarding.

The coordinator remains the existing Docker Compose deployment. A guided first-install
command collects its hostname and Google OAuth configuration, generates local secrets
and invokes the existing checksum-verified installer. It does not provision DNS,
purchase hosting or create Google credentials. Existing installations retain their
explicit upgrade and backup path.

Dependencies: pystray provides native status-area integration; Pillow supplies its
small generated icon. Tk and the current Python runtime/controller are retained.
Native macOS builds still require Developer ID signing and Apple notarization for
ordinary Gatekeeper-approved distribution. Unsigned candidates are labeled accordingly.

Acceptance: automatic approval exchange and restart; origin-bound secure storage;
pause/quit and offline retry; invalid/revoked credentials; existing worker protocol;
one-host proxy isolation; operator-specified HTTPS origins; guided setup validation;
native Windows packaging; native macOS CI and explicit signing limitations.
