"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ConfirmAction, DataTable, JsonDetails } from "./operational";
import type { Snapshot } from "../lib/contracts";

export interface Account {
  id: string;
  email: string;
  display_name: string;
  roles: string[];
  permissions: string[];
  enabled: boolean;
  picture: string | null;
}
interface Invitation {
  id: string;
  email: string;
  roles: string[];
  expires_at: string;
  revoked: boolean;
  used_by: string | null;
}
interface Membership {
  owner_id: string;
  shared: boolean;
  members: { user_id: string; role: string }[];
  allowed_models: string[] | null;
  allowed_tools: string[] | null;
}
interface MachineCredential {
  id: string;
  name: string;
  revoked: boolean;
  node_id: string | null;
}
async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/control/${path}`, {
    method: body === undefined ? "GET" : "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) window.location.assign("/?auth=required");
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "Session expired or revoked. Sign in again."
        : response.status === 403
          ? "Permission denied."
          : "Operation not confirmed; check backend availability and permissions.",
    );
  return response.json() as Promise<T>;
}
const csv = (value: FormDataEntryValue | null) =>
  String(value ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

export default function Administration({
  initialUser,
}: {
  initialUser: Account;
}) {
  const [user, setUser] = useState(initialUser);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [credentials, setCredentials] = useState<MachineCredential[] | null>(
    null,
  );
  const [audit, setAudit] = useState<
    | {
        id: string;
        actor_id: string | null;
        action: string;
        timestamp: string;
        details: unknown;
        correlation_id: string | null;
      }[]
    | null
  >(null);
  const [workspace, setWorkspace] = useState("");
  const [membership, setMembership] = useState<Membership | null>(null);
  const [secret, setSecret] = useState<unknown>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const platform = user.permissions.includes("platform.manage");
  const load = useCallback(async () => {
    const current = await call<Account>("auth/me");
    setUser(current);
    setSnapshot(await call<Snapshot>("command-center"));
    setCredentials(
      await call<MachineCredential[]>(
        `administration/node-credentials?offset=${offset}`,
      ),
    );
    if (current.permissions.includes("platform.manage")) {
      const [users, invites, events] = await Promise.all([
        call<Account[]>(`administration/users?offset=${offset}`),
        call<Invitation[]>(`administration/invitations?offset=${offset}`),
        call<NonNullable<typeof audit>>(
          `administration/audit?offset=${offset}`,
        ),
      ]);
      setAccounts(users);
      setInvitations(invites);
      setAudit(events);
    } else {
      setAccounts(null);
      setInvitations(null);
      setAudit(null);
    }
  }, [offset]);
  useEffect(() => {
    async function refresh() {
      try {
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Refresh failed.");
      }
    }
    void refresh();
  }, [load]);
  useEffect(() => {
    let active = true;
    if (workspace)
      void call<Membership>(`administration/workspaces/${workspace}/members`)
        .then((data) => {
          if (active) setMembership(data);
        })
        .catch((e) => {
          if (active) setError(String(e.message));
        });
    return () => {
      active = false;
    };
  }, [workspace]);
  async function operate(path: string, body: unknown, oneTime = false) {
    setBusy(true);
    setError("");
    setSecret(null);
    try {
      const result = await call(path, body);
      if (oneTime) setSecret(result);
      await load();
      if (workspace)
        setMembership(
          await call<Membership>(
            `administration/workspaces/${workspace}/members`,
          ),
        );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed.");
    } finally {
      setBusy(false);
    }
  }
  function form(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    return new FormData(event.currentTarget);
  }
  const selected = snapshot?.workspaces.find((w) => w.id === workspace);
  return (
    <main id="main-content" className="command-body administration-page">
      <div className="page-heading">
        <div>
          <a href="/">The Godfather / Command Center</a>
          <h1>Account / Administration</h1>
          <p>Persisted identities, owner permissions and security history.</p>
        </div>
        <button
          className="action"
          disabled={busy}
          onClick={() => void load().catch((e) => setError(e.message))}
        >
          Refresh
        </button>
      </div>
      {error && (
        <p role="alert" className="notice error">
          {error} <a href="/">Return to sign-in</a>
        </p>
      )}
      {busy && <p role="status">Waiting for backend confirmation…</p>}
      <section className="panel">
        <h2>Your account</h2>
        <p>
          {user.display_name} · {user.email}
        </p>
        <p>
          {user.roles.join(", ")} · Account ID {user.id}
        </p>
        <ConfirmAction
          label="Revoke all my sessions"
          description="Sign out every application session for your account. Google sessions remain independent."
          onConfirm={async () => {
            const response = await fetch("/api/auth/revoke", {
              method: "POST",
            });
            if (!response.ok) throw new Error("Revocation not confirmed");
            window.location.assign("/");
          }}
        />
        <button
          className="action"
          onClick={async () => {
            const response = await fetch("/api/auth/logout", {
              method: "POST",
            });
            if (response.ok) window.location.assign("/");
            else setError("Logout not confirmed.");
          }}
        >
          Sign out
        </button>
      </section>
      {secret !== null && (
        <section className="panel">
          <h2>One-time delivery</h2>
          <p>
            Deliver this secret through an approved private channel. It will not
            be shown again. Never paste it into logs or source control.
          </p>
          <pre>{JSON.stringify(secret, null, 2)}</pre>
          <button className="action" onClick={() => setSecret(null)}>
            Dismiss secret
          </button>
        </section>
      )}
      <section className="panel">
        <h2>Workspaces</h2>
        {!snapshot ? (
          <p role="status">Loading authorized workspaces…</p>
        ) : (
          <label>
            Workspace
            <select
              value={workspace}
              onChange={(e) => {
                setMembership(null);
                setWorkspace(e.target.value);
              }}
            >
              <option value="">Select workspace</option>
              {snapshot.workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <form
          method="post"
          onSubmit={(e) => {
            const f = form(e);
            void operate("administration/workspaces", { name: f.get("name") });
          }}
        >
          <label>
            New private workspace name
            <input name="name" required maxLength={200} />
          </label>
          <button className="action" disabled={busy}>
            Create workspace
          </button>
        </form>
        {membership && (
          <>
            <p>
              Owner {membership.owner_id} ·{" "}
              {membership.shared ? "Explicitly shared" : "Private"}
            </p>
            <DataTable
              caption="Workspace members"
              rows={membership.members}
              rowKey={(m) => m.user_id}
              columns={[
                { label: "Account ID", cell: (m) => m.user_id },
                { label: "Role", cell: (m) => m.role },
              ]}
            />
            <JsonDetails
              label="Workspace model and tool permissions"
              value={{
                models: membership.allowed_models,
                tools: membership.allowed_tools,
              }}
            />
          </>
        )}
        {selected?.can_manage && (
          <>
            <form
              method="post"
              onSubmit={(e) => {
                const f = form(e);
                if (window.confirm("Apply this workspace membership change?"))
                  void operate(
                    `administration/workspaces/${workspace}/members`,
                    { user_id: f.get("user_id"), role: f.get("role") },
                  );
              }}
            >
              <label>
                Invited account ID
                <input name="user_id" required />
              </label>
              <label>
                Workspace role
                <select name="role">
                  <option value="member">Member</option>
                  <option value="admin">Workspace administrator</option>
                  <option value="remove">Remove access</option>
                </select>
              </label>
              <button className="action" disabled={busy}>
                Apply membership
              </button>
            </form>
            <form
              method="post"
              key={workspace}
              onSubmit={(e) => {
                const f = form(e);
                if (
                  window.confirm(
                    "Apply model and tool restrictions? Active execution rechecks these permissions.",
                  )
                )
                  void operate(
                    `administration/workspaces/${workspace}/policy`,
                    {
                      allowed_models: csv(f.get("models")),
                      allowed_tools: csv(f.get("tools")),
                    },
                  );
              }}
            >
              <label>
                Allowed exact model identifiers (comma separated)
                <input
                  name="models"
                  defaultValue={membership?.allowed_models?.join(", ") ?? ""}
                />
              </label>
              <label>
                Allowed read-only tools (name@version, comma separated)
                <input
                  name="tools"
                  defaultValue={membership?.allowed_tools?.join(", ") ?? ""}
                />
              </label>
              <button className="action" disabled={busy}>
                Apply execution policy
              </button>
              <p>
                Empty lists deny model/tool use. Exact model selection is
                required under a model allowlist. Node-owner grants also apply.
              </p>
            </form>
          </>
        )}
      </section>
      {(user.permissions.includes("nodes.contribute") ||
        !!credentials?.length) && (
        <section className="panel">
          <h2>Owned node onboarding</h2>
          <p>
            Generate a machine credential for a worker you own. Configure
            contribution limits and tool grants in the worker’s private local
            configuration. Machine credentials are independent of Google login.
          </p>
          {user.permissions.includes("nodes.contribute") && (
            <form
              method="post"
              onSubmit={(e) => {
                const f = form(e);
                void operate(
                  "administration/node-credentials",
                  { name: f.get("name") },
                  true,
                );
              }}
            >
              <label>
                Unique node name
                <input name="name" required maxLength={100} />
              </label>
              <button className="action" disabled={busy}>
                Create worker credential
              </button>
            </form>
          )}
          {credentials && (
            <DataTable
              caption="Owned worker credentials"
              rows={credentials}
              rowKey={(c) => c.id}
              columns={[
                {
                  label: "Node / credential",
                  cell: (c) => (
                    <>
                      {c.name}
                      <small>{c.id}</small>
                    </>
                  ),
                },
                {
                  label: "Status",
                  cell: (c) =>
                    c.revoked
                      ? "Revoked"
                      : c.node_id
                        ? "Registered"
                        : "Awaiting registration",
                },
                {
                  label: "Control",
                  cell: (c) =>
                    c.revoked ? (
                      "Unavailable"
                    ) : (
                      <ConfirmAction
                        label="Revoke worker credential"
                        description="Permanently invalidate this owned machine credential, including one not yet registered."
                        onConfirm={() =>
                          operate(
                            `administration/node-credentials/${c.id}/revoke`,
                            {},
                          )
                        }
                      />
                    ),
                },
              ]}
            />
          )}
          <a href="/nodes">Inspect and control registered nodes</a>
          {!platform && (
            <div className="actions">
              <button
                className="action"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous credentials
              </button>
              <button
                className="action"
                disabled={(credentials?.length ?? 0) < 100}
                onClick={() => setOffset(offset + 100)}
              >
                Next credentials
              </button>
            </div>
          )}
        </section>
      )}
      {platform && (
        <>
          <section className="panel">
            <h2>Invitations</h2>
            <form
              method="post"
              onSubmit={(e) => {
                const f = form(e);
                void operate(
                  "administration/invitations",
                  {
                    email: f.get("email"),
                    roles: f.getAll("roles"),
                    hours: Number(f.get("hours")),
                  },
                  true,
                );
              }}
            >
              <label>
                Google account email
                <input name="email" type="email" required maxLength={320} />
              </label>
              <RoleChoices selected={["member"]} />
              <label>
                Valid hours
                <input
                  name="hours"
                  type="number"
                  min={1}
                  max={168}
                  defaultValue={24}
                  required
                />
              </label>
              <button className="action" disabled={busy}>
                Create invitation
              </button>
            </form>
            {invitations === null ? (
              <p>Loading invitations…</p>
            ) : (
              <DataTable
                caption="Persisted invitations"
                rows={invitations}
                rowKey={(i) => i.id}
                columns={[
                  {
                    label: "Email / roles",
                    cell: (i) => `${i.email} · ${i.roles.join(", ")}`,
                  },
                  {
                    label: "Status",
                    cell: (i) =>
                      i.revoked
                        ? "Revoked"
                        : i.used_by
                          ? "Used"
                          : new Date(i.expires_at) <= new Date()
                            ? "Expired"
                            : `Expires ${new Date(i.expires_at).toLocaleString()}`,
                  },
                  {
                    label: "Control",
                    cell: (i) =>
                      !i.revoked && !i.used_by ? (
                        <ConfirmAction
                          label="Revoke invitation"
                          description="Permanently prevent this unused invitation from activating an account."
                          onConfirm={() =>
                            operate(
                              `administration/invitations/${i.id}/revoke`,
                              {},
                            )
                          }
                        />
                      ) : (
                        "Unavailable"
                      ),
                  },
                ]}
              />
            )}
          </section>
          <section className="panel">
            <h2>Users</h2>
            <p>
              Google-linked application identities. Existing local identities
              require explicit offline linking; ownership and history are
              preserved.
            </p>
            {accounts === null ? (
              <p>Loading users…</p>
            ) : accounts.length === 0 ? (
              <p>No linked users.</p>
            ) : (
              accounts.map((account) => (
                <form
                  method="post"
                  className="panel"
                  key={
                    account.id + account.roles.join() + String(account.enabled)
                  }
                  onSubmit={(e) => {
                    const f = form(e);
                    if (
                      window.confirm(
                        "Apply roles/account status and revoke this user’s sessions?",
                      )
                    )
                      void operate(`administration/users/${account.id}`, {
                        roles: f.getAll("roles"),
                        enabled: f.has("enabled"),
                      });
                  }}
                >
                  <h3>{account.display_name}</h3>
                  <p>
                    {account.email} · {account.id}
                  </p>
                  <RoleChoices selected={account.roles} />
                  <label>
                    <input
                      type="checkbox"
                      name="enabled"
                      defaultChecked={account.enabled}
                    />{" "}
                    Account enabled
                  </label>
                  <button className="action" disabled={busy}>
                    Save account and revoke sessions
                  </button>
                  <ConfirmAction
                    label="Revoke user sessions"
                    description="Invalidate every application session for this user."
                    onConfirm={() =>
                      operate(
                        `administration/users/${account.id}/revoke-sessions`,
                        {},
                      )
                    }
                  />
                </form>
              ))
            )}
          </section>
          <section className="panel">
            <h2>Security audit</h2>
            {audit === null ? (
              <p>Loading audit history…</p>
            ) : (
              <DataTable
                caption="Durable security events"
                rows={audit}
                rowKey={(e) => e.id}
                columns={[
                  {
                    label: "Time",
                    cell: (e) => new Date(e.timestamp).toLocaleString(),
                  },
                  {
                    label: "Actor / action",
                    cell: (e) =>
                      `${e.actor_id ?? "Unauthenticated"} · ${e.action}`,
                  },
                  {
                    label: "Details / correlation",
                    cell: (e) => (
                      <>
                        <JsonDetails
                          label="Outcome and target"
                          value={e.details}
                        />
                        {e.correlation_id}
                      </>
                    ),
                  },
                ]}
              />
            )}
          </section>
          <div className="actions">
            <button
              className="action"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              Previous 100
            </button>
            <span>Records from {offset + 1}</span>
            <button
              className="action"
              disabled={
                !accounts ||
                Math.max(
                  accounts.length,
                  invitations?.length ?? 0,
                  audit?.length ?? 0,
                  credentials?.length ?? 0,
                ) < 100
              }
              onClick={() => setOffset(offset + 100)}
            >
              Next 100
            </button>
          </div>
        </>
      )}
    </main>
  );
}

export function RoleChoices({ selected }: { selected: string[] }) {
  return (
    <fieldset className="role-choices">
      <legend>Platform roles</legend>
      {["platform_admin", "contributor", "member"].map((role) => (
        <label key={role}>
          <input
            type="checkbox"
            name="roles"
            value={role}
            defaultChecked={selected.includes(role)}
          />
          {role.replaceAll("_", " ")}
        </label>
      ))}
    </fieldset>
  );
}
