# Consigliere for Mac — The Godfather AI

Quit the existing worker from its tray menu before upgrading. Open the DMG and
run **Install Consigliere.command**, then **Install / replace existing version**.
Open Consigliere from Applications after installation and eject the DMG. The
installer replaces the existing app, including its former The Godfather Worker
name; it preserves the Keychain identity and local settings. New per-user installs
use `~/Applications`. It does not request elevation or change folder permissions.
Enter your Command Center address and click **Connect**. Sign in using your
invited Google account, compare the code and approve this computer. It connects
automatically. No credential file, invitation code or Tailscale setup is needed
with the new HTTPS coordinator release.

Enable **Allow my existing local AI models** if you want to contribute installed
Ollama models. Nothing is downloaded automatically. Close the window to keep the
worker in the menu bar. Pause, Resume, Open Command Center and Quit are available
there. Advanced settings contain contribution limits and explicit sharing scopes.

This is an ad-hoc signed development candidate. No Apple Developer ID certificate
or notarization credentials were supplied. macOS may block normal installation.
Production distribution requires Developer ID Application signing and Apple
notarization; contributors do not need developer credentials. Do not disable
Gatekeeper to treat this candidate as an approved production download.

See [troubleshooting](TROUBLESHOOTING.md) and the repository's
`docs/operations/simple-onboarding.md` for validation and activation limits.
