# Simple workspace contribution

Accepted for owner-requested implementation, 2026-10-22.

Normal onboarding is install, Connect, approve the matching browser code, and
contribute. A visible local choice, **Contribute this computer to my workspaces**,
replaces manual user/workspace ID lists. On a fresh, unpaired installation it is
selected before the owner explicitly connects and approves the computer. It enables
existing local model discovery and advertises detected capacity. No model, runtime,
service or API key is installed or enabled by that choice.

Existing settings, identities, resource allowances and restricted sharing lists
retain their exact meaning. An existing private computer is never opted in by an
upgrade. Its owner enables the new switch once. Changing contributions is applied
by the existing idle-maintenance mechanism: finish the active attempt, re-register
under the same saved computer identity, then resume automatically. Pause or Quit
cancels an outstanding automatic restart. Disabling shared contribution preserves
the owner's ability to run their own jobs.

The additive registration field `share_with_workspaces` is false by default and
omitted from legacy false advertisements. Only authenticated worker registration
sets or withdraws this consent; an administrator cannot set it on another owner's
computer. The flag persists in the existing PostgreSQL node contribution policy,
so no new service or schema migration is required. An older registration clears it
rather than accidentally preserving a stale permission. Update the coordinator
before publishing workers that use the new opt-in.

The common scheduler permission predicate requires both the submitter and computer
owner to have current access to the job's workspace. With local workspace
contribution enabled and a non-dedicated policy, this membership replaces the two
explicit sharing allowlists. It covers current and future joined workspaces and
their members; leaving, disabling the account or withdrawing contribution takes
effect on subsequent claims, delivery and reports. Local consent includes this
dynamic membership scope. Workspace owners control invitations through the existing
named-user/email flow. Legacy explicit lists still work without broadening.

All workload authorization is still checked: allowed workspace models/tools,
installed capabilities, repository/file grants, paid-model consent, per-owner API
connections, resource compatibility, leases and fences. Contributing a computer
does not share its account API keys or grant another owner access to private files.
The distributed submission API now distinguishes a disabled workspace model or
unauthorized API connection from contribution permission, rather than presenting
all three as a missing sharing grant.

Acceptance includes ordinary and distributed cross-user execution with empty ID
lists, joining a workspace after registration, active-report denial after leaving,
local opt-out, default/legacy protocol compatibility, separate paid-provider consent,
fresh and existing native onboarding, no model-ready claim without an available
model, and automatic reconfiguration without cancelling the active attempt.
