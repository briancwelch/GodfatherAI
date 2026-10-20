# The Godfather Worker for Mac

**Release status: unsigned development candidate; ordinary distribution pending.**
GitHub Actions builds require both native architecture checks to pass. These builds
have no Developer ID signature or notarization and may be blocked by Gatekeeper.
Your administrator must provide a tested, signed installer for ordinary use after
the server update is approved. These instructions describe the candidate app.

## Install and connect

1. Ask your administrator for an invitation, the installer matching your Mac
   (Apple Silicon or Intel), and help connecting Tailscale. They must also finish
   the private connection setup for your Mac. No router changes are needed.
2. Download the approved `.dmg` from the location your administrator provides.
   Open it. In Finder, open your Home folder and its **Applications** folder
   (create that folder if needed). Drag **The Godfather Worker.app** there.
3. Open **The Godfather Worker**. Click **Connect to The Godfather**.
4. In your browser, choose **Continue with Google**. Use your invited account;
   enter your invitation token if this is your first sign-in. Google signs you
   in to The Godfather; it does not give other users access to your Mac.
5. Compare the code shown in the browser with the app. Give the Mac a name,
   tick the confirmation, and click **Approve this Mac**. Return to the app and
   click **Finish connecting** within five minutes. Allow Keychain access if asked.
6. Choose your contribution settings. The default is one job at a time, shared
   work off, and local inference off. CPU/RAM scheduling budgets are **not hard
   usage limits**. Enable existing Ollama models only if you want local inference;
   nothing is downloaded. CPU-only mode connects without running jobs or tools.
7. Click **Start Worker**. Wait for **Connected**, then visit
   [The Godfather](https://app.the-godfather.ai) and check that your named Mac is
   online under **Nodes**. The app shows actual job activity when it receives work.

## Stop, update, or remove

- Click **Stop / Pause Worker** to pause. Click **Start Worker** to resume;
  restarting may wait about 30 seconds for the previous connection to expire.
- **Start the app and worker at login** is optional and uses your saved settings.
- To update, quit the app and replace it with the approved newer app. Keep the
  same Mac account. Your identity stays in Keychain and your settings are retained.
- To remove, stop the worker. In Command Center, open **Administration → Owned
  node onboarding** and choose **Revoke worker credential** for this Mac. In the
  app, click **Forget this Mac locally…**, then quit and move the app to Trash.
  This removes its identity, settings and login startup entry; your own models,
  documents and other applications are preserved.

## If something goes wrong

- **Cannot connect / access refused:** connect Tailscale and ask your administrator
  to check your invitation and this Mac's private connection setup.
- **Approval unavailable:** click Connect again and approve a fresh matching code.
  If Finish connecting lost its connection, ask the owner to revoke any pending
  Mac entry before trying again. Never copy machine credentials manually.
- **Keychain error:** unlock your login Keychain and allow access. Ask the owner
  to revoke the pending Mac entry before reconnecting if saving failed.
- **No models:** you can still connect. Inference needs a separately installed,
  running compatible local runtime and existing models.
- **macOS cannot verify the app:** request a signed, notarized installer. Do not
  disable macOS security settings. An unsigned development candidate needs further
  release work and is not the ordinary installation path.

Use **Diagnostics** for connection details. Send those details to your administrator;
never send passwords, Keychain contents, or private documents.
