# Administrator: invite and approve a Mac worker

This is a preparation guide. No installer is ready to send until native acceptance
and signing are complete, and the new enrollment routes are deployed with approval.

1. Review the candidate, tests, migration and private-network prerequisites. Obtain
   separate approval for deployment; this task does not deploy anything.
2. In Command Center **Administration**, create an invitation for the contributor's
   exact Google email with the contributor role. Share it privately through your
   authorized channel. No invitation was created or sent by this implementation.
3. With the node owner's consent, arrange Tailscale membership, a narrow outbound
   grant to the coordinator on TCP 443, and private resolution of
   `api.the-godfather.ai`. Verify the real certificate. Do not expose the public
   worker routes or change unrelated network settings to make enrollment easier.
4. After native clean-host acceptance and distribution approval, provide the
   correct Apple Silicon or Intel DMG, checksum and end-user README. The installer
   contains no user, machine or Google credentials.
5. The contributor starts Connect on their own Mac, signs in with Google, compares
   the app/browser code, names the Mac and approves it. Ownership comes from their
   session. An administrator cannot approve a node as a different owner.
6. The contributor finishes connecting, chooses local limits and clicks Start.
   Check **Nodes** for its actual owner, platform, heartbeat and online status.
   CPU-only enrollment does not execute jobs. For optional inference, submit an
   authorized job using an existing local model and verify its actual result.
7. To revoke, the owner opens **Administration → Owned node onboarding → Revoke
   worker credential**. This also covers an entry awaiting first registration.
   An authorized platform administrator can use existing node controls where
   permitted; administrative status never grants private host access.

If approval is unused, the owner can click **Cancel pairing approval** in the
browser. If exchange lost its response or Keychain saving failed, revoke the
pending machine credential before retrying with a fresh code/name. Revoked names
remain reserved under the existing identity contract; use a new name. Removing
the app alone does not revoke its remote credential. Removing contributor access
must also revoke invitations, application sessions and machine credentials and
remove separately approved tailnet grants, without deleting the owner's data.
