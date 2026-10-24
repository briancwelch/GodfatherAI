"use client";

import { control, ControlError } from "../lib/control-client";
import { useFeedback } from "./toast-notifications";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { ApplicationShell, RibbonGroup } from "./application-shell";
import {
  ConfirmAction,
  DataTable,
  JsonDetails,
  Pager,
  SectionTabs,
} from "./operational";
import { UserName } from "./node-identity";
import { AppearanceSettings } from "./appearance-settings";
import { NodeRegistrationSettings } from "./node-registration-settings";
import { BulkTable } from "./bulk-table";
import type { Page, Snapshot } from "../lib/contracts";
import { ConnectComputer } from "./connect-computer";
import { Avatar } from "./avatar";

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
export function InvitationDelivery({ invitation }: { invitation: Invitation }) {
  const [message, setMessage] = useState("");
  return (
    <div>
      <span>No email sent · Share sign-in instructions</span>{" "}
      <button
        className="btn btn-outline-primary"
        type="button"
        onClick={async () => {
          const instructions = `You are invited to The Godfather. Open ${window.location.origin}/ and select Continue with Google using ${invitation.email}. No invitation code is needed. Accept before ${new Date(invitation.expires_at).toLocaleString()}. Tailscale access is separate.`;
          try {
            await navigator.clipboard.writeText(instructions);
            setMessage("Sign-in instructions copied.");
          } catch {
            setMessage(instructions);
          }
        }}
      >
        Copy sign-in instructions
      </button>
      {message && <p role="status">{message}</p>}
    </div>
  );
}
interface Membership {
  total: number;
  limit: number;
  offset: number;
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
  try {
    return await control<T>(path, body);
  } catch (error) {
    if (error instanceof ControlError && error.status === 401)
      window.location.assign("/?auth=required");
    throw error;
  }
}

export default function Administration({
  initialUser,
  initialTab,
}: {
  initialTab?: string;
  initialUser: Account;
}) {
  const [tab, setTab] = useState(
    initialTab ||
      (initialUser.permissions.includes("platform.manage")
        ? "Users"
        : "Settings"),
  );
  const [pages, setPages] = useState<Record<string, number>>({});
  const [page, setPage] = useState<{ total: number; limit: number } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [memberOffset, setMemberOffset] = useState(0);
  const generation = useRef(0);
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
        actor_name?: string | null;
        actor_picture?: string | null;
        action: string;
        timestamp: string;
        details: unknown;
        correlation_id: string | null;
      }[]
    | null
  >(null);
  const [workspace, setWorkspace] = useState("");
  const [catalog, setCatalog] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [membership, setMembership] = useState<Membership | null>(null);
  const [secret, setSecret] = useState<unknown>(null);
  const [invited, setInvited] = useState<Invitation | null>(null);
  const [error, setError] = useState("");
  useFeedback(error);
  const [busy, setBusy] = useState(false);
  const offset = pages[tab] || 0;
  const setOffset = (value: number) =>
    setPages((p) => ({ ...p, [tab]: value }));
  const tabs = [
    "Settings",
    "Workspaces",
    "Permissions",
    "Computers",
    ...(user.permissions.includes("platform.manage")
      ? ["Users", "Invitations", "Node permissions", "Appearance", "Audit"]
      : []),
  ];
  const platform = user.permissions.includes("platform.manage");
  const load = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const [current, registry, nextSnapshot] = await Promise.all([
        call<Account>("auth/me"),
        call<{ reference: { name: string; version: number } }[]>("tools"),
        call<Snapshot>("command-center"),
      ]);
      if (request !== generation.current) return;
      setUser(current);
      setTools(
        registry.map((t) => `${t.reference.name}@${t.reference.version}`),
      );
      setSnapshot(nextSnapshot);
      const endpoint = (
        {
          Users: "users",
          Invitations: "invitations",
          Audit: "audit",
          Computers: "node-credentials",
        } as Record<string, string>
      )[tab];
      if (
        endpoint &&
        (tab === "Computers" || current.permissions.includes("platform.manage"))
      ) {
        const result = await call<
          Page<
            | Account
            | Invitation
            | MachineCredential
            | NonNullable<typeof audit>[number]
          >
        >(`administration/${endpoint}?paged=true&offset=${offset}`);
        if (request !== generation.current) return;
        setPage(result);
        if (tab === "Users") setAccounts(result.items as Account[]);
        if (tab === "Invitations") setInvitations(result.items as Invitation[]);
        if (tab === "Computers")
          setCredentials(result.items as MachineCredential[]);
        if (tab === "Audit")
          setAudit(result.items as NonNullable<typeof audit>);
      } else setPage(null);
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, [offset, tab]);
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
      void call<Membership>(
        `administration/workspaces/${workspace}/members?offset=${memberOffset}`,
      )
        .then((data) => {
          if (active) setMembership(data);
          return call<{ catalog: { identifier: string }[] }>(
            `models/install-options?workspace_id=${workspace}`,
          );
        })
        .then((options) => {
          if (active) setCatalog(options.catalog.map((m) => m.identifier));
        })
        .catch((e) => {
          if (active) setError(String(e.message));
        });
    return () => {
      active = false;
    };
  }, [workspace, memberOffset]);
  async function operate(path: string, body: unknown, oneTime = false) {
    setBusy(true);
    setError("");
    setSecret(null);
    setInvited(null);
    try {
      const result = await call(path, body);
      if (path === "administration/invitations")
        setInvited(result as Invitation);
      if (oneTime) setSecret(result);
      await load();
      if (workspace)
        setMembership(
          await call<Membership>(
            `administration/workspaces/${workspace}/members?offset=${memberOffset}`,
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
    <ApplicationShell
      section="administration"
      data={snapshot}
      account={user}
      refresh={() => void load().catch((e) => setError(e.message))}
      ribbon={
        <RibbonGroup label="Administration">
          {[
            "Users",
            "Invitations",
            "Workspaces",
            "Permissions",
            "Settings",
          ].map((label) => (
            <button
              className="btn btn-outline-primary action secondary"
              key={label}
              disabled={!platform && ["Users", "Invitations"].includes(label)}
              aria-pressed={tab === label}
              onClick={() => setTab(label)}
            >
              {label}
            </button>
          ))}
        </RibbonGroup>
      }
    >
      <main
        id="main-content"
        className="container-fluid command-body administration-page"
      >
        <div className="page-heading">
          <div>
            <a href="/">The Godfather / Command Center</a>
            <h1>Admin settings</h1>
            <p>Persisted identities, owner permissions and security history.</p>
          </div>
          <button
            className="btn btn-primary action"
            disabled={busy}
            onClick={() => void load().catch((e) => setError(e.message))}
          >
            Refresh
          </button>
        </div>
        {error && (
          <p role="alert" className="alert alert-danger notice error">
            {error} <a href="/">Return to sign-in</a>
          </p>
        )}
        {busy && <p role="status">Waiting for backend confirmation…</p>}
        {platform && (
          <a href="/administration/appearance">Configure site appearance</a>
        )}
        <SectionTabs
          label="Administration sections"
          tabs={tabs}
          value={tab}
          onChange={setTab}
        />
        {loading && <p role="status">Loading {tab.toLowerCase()}…</p>}
        <div aria-busy={loading} inert={loading}>
          {page && !loading && (
            <Pager
              offset={offset}
              limit={page.limit}
              total={page.total}
              onChange={setOffset}
            />
          )}
          <section
            role="tabpanel"
            aria-label="Settings"
            hidden={tab !== "Settings"}
            className="card panel"
          >
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
              className="btn btn-primary action"
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
            <section className="card panel">
              <h2>One-time delivery</h2>
              <p>
                Deliver this secret through an approved private channel. It will
                not be shown again. Never paste it into logs or source control.
              </p>
              <pre>{JSON.stringify(secret, null, 2)}</pre>
              <button
                className="btn btn-primary action"
                onClick={() => setSecret(null)}
              >
                Dismiss secret
              </button>
            </section>
          )}
          <section
            role="tabpanel"
            aria-label={tab === "Permissions" ? "Permissions" : "Workspaces"}
            hidden={!["Workspaces", "Permissions"].includes(tab)}
            className="card panel"
          >
            <h2>{tab === "Permissions" ? "Permissions" : "Workspaces"}</h2>
            {!snapshot ? (
              <p role="status">Loading authorized workspaces…</p>
            ) : (
              <label>
                Workspace
                <select
                  className="form-select"
                  value={workspace}
                  onChange={(e) => {
                    setMembership(null);
                    setWorkspace(e.target.value);
                    setMemberOffset(0);
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
            {tab === "Workspaces" && snapshot && (
              <BulkTable
                kind="workspaces"
                scope="workspaces"
                rows={snapshot.workspaces}
                caption="Authorized workspaces"
                rowKey={(w) => w.id}
                deleteKey={(w) => w.id}
                label={(w) => `workspace ${w.name}`}
                eligible={(w) => w.owner_id === user.id}
                onDeleted={async () => {
                  setWorkspace("");
                  setMembership(null);
                  await load();
                }}
                columns={[
                  { label: "Workspace", cell: (w) => w.name },
                  {
                    label: "Owner",
                    cell: (w) => (w.owner_id === user.id ? "You" : w.owner_id),
                  },
                  {
                    label: "Access",
                    cell: (w) => (w.can_manage ? "Administrator" : "Member"),
                  },
                ]}
              />
            )}
            <form
              hidden={tab !== "Workspaces"}
              method="post"
              onSubmit={(e) => {
                const f = form(e);
                void operate("administration/workspaces", {
                  name: f.get("name"),
                });
              }}
            >
              <label>
                New private workspace name
                <input
                  className="form-control"
                  name="name"
                  required
                  maxLength={200}
                />
              </label>
              <button className="btn btn-primary action" disabled={busy}>
                Create workspace
              </button>
            </form>
            {tab === "Permissions" && membership && (
              <>
                <p>
                  Owner {membership.owner_id} ·{" "}
                  {membership.shared ? "Explicitly shared" : "Private"}
                </p>
                <Pager
                  offset={memberOffset}
                  limit={membership.limit}
                  total={membership.total}
                  onChange={setMemberOffset}
                />
                <DataTable
                  caption="Workspace members"
                  rows={membership.members}
                  rowKey={(m) => m.user_id}
                  columns={[
                    { label: "Account ID", cell: (m) => m.user_id },
                    { label: "Role", cell: (m) => m.role },
                  ]}
                />
                <Pager
                  offset={memberOffset}
                  limit={membership.limit}
                  total={membership.total}
                  onChange={setMemberOffset}
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
            {tab === "Permissions" && selected?.can_manage && (
              <>
                <PermissionEditor
                  key={workspace}
                  workspace={workspace}
                  platform={platform}
                  members={membership?.members || []}
                  onUpdated={async () => {
                    setMembership(
                      await call<Membership>(
                        `administration/workspaces/${workspace}/members?offset=${memberOffset}`,
                      ),
                    );
                  }}
                />
                <form
                  method="post"
                  key={`${workspace}:${JSON.stringify(membership?.allowed_models)}:${JSON.stringify(membership?.allowed_tools)}`}
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
                          allowed_models: f.getAll("models"),
                          allowed_tools: f.getAll("tools"),
                        },
                      );
                  }}
                >
                  <fieldset>
                    <legend>Allowed models</legend>
                    {[
                      ...new Set([
                        ...catalog,
                        ...(snapshot?.models || []).map(
                          (m) => m.deployment.identifier,
                        ),
                        ...(membership?.allowed_models || []),
                      ]),
                    ].map((model) => (
                      <label className="check-label" key={model}>
                        <input
                          className="form-check-input"
                          type="checkbox"
                          name="models"
                          value={model}
                          defaultChecked={membership?.allowed_models?.includes(
                            model,
                          )}
                        />
                        {model}
                      </label>
                    ))}
                  </fieldset>
                  <fieldset>
                    <legend>Allowed read-only tools</legend>
                    {[
                      ...new Set([
                        ...tools,
                        ...(membership?.allowed_tools || []),
                      ]),
                    ].map((tool) => (
                      <label className="check-label" key={tool}>
                        <input
                          className="form-check-input"
                          type="checkbox"
                          name="tools"
                          value={tool}
                          defaultChecked={membership?.allowed_tools?.includes(
                            tool,
                          )}
                        />
                        {tool}
                      </label>
                    ))}
                  </fieldset>
                  <button className="btn btn-primary action" disabled={busy}>
                    Apply execution policy
                  </button>
                  <p>
                    Empty lists deny model/tool use. Exact model selection is
                    required under a model allowlist. Node-owner grants also
                    apply.
                  </p>
                </form>
              </>
            )}
          </section>
          {(user.permissions.includes("nodes.contribute") ||
            !!credentials?.length) && (
            <section
              role="tabpanel"
              aria-label="Computers"
              hidden={tab !== "Computers"}
              className="card panel"
            >
              <ConnectComputer />
              <h2>Owned computers and credentials</h2>
              <p>
                The desktop app creates and saves its credential automatically
                after your browser approval. Revoke a lost or retired computer
                below.
              </p>
              {user.permissions.includes("nodes.add") && (
                <details>
                  <summary>
                    Advanced: manual command-line worker credential
                  </summary>
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
                      <input
                        className="form-control"
                        name="name"
                        required
                        maxLength={100}
                      />
                    </label>
                    <button className="btn btn-primary action" disabled={busy}>
                      Create worker credential
                    </button>
                  </form>
                </details>
              )}
              {credentials && (
                <BulkTable
                  kind="node-credentials"
                  scope={`computers:${user.id}:${offset}`}
                  deleteKey={(c: MachineCredential) => c.id}
                  label={(c: MachineCredential) => c.name}
                  eligible={() => !busy && !loading}
                  onDeleted={async () => {
                    await load();
                    if (offset) setOffset(0);
                  }}
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
                      cell: (c) => (
                        <div className="actions">
                          <ConfirmAction
                            label="Delete credential"
                            disabled={busy || loading}
                            description={`Delete ${c.name}? Access is permanently revoked; node and audit history and local files are retained.`}
                            onConfirm={async () => {
                              await call("administration/bulk-delete", {
                                kind: "node-credentials",
                                ids: [c.id],
                              });
                              await load();
                              if (offset) setOffset(0);
                            }}
                          />
                          {!c.revoked && (
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
                          )}
                        </div>
                      ),
                    },
                  ]}
                />
              )}
              <a href="/nodes">Inspect and control registered nodes</a>
            </section>
          )}
          {platform && (
            <>
              <section
                role="tabpanel"
                aria-label="Node permissions"
                hidden={tab !== "Node permissions"}
              >
                {tab === "Node permissions" && <NodeRegistrationSettings />}
              </section>
              <section
                role="tabpanel"
                aria-label="Appearance"
                hidden={tab !== "Appearance"}
              >
                {tab === "Appearance" && <AppearanceSettings />}
              </section>
              <section
                role="tabpanel"
                aria-label="Invitations"
                hidden={tab !== "Invitations"}
                className="card panel"
              >
                <h2>Invitations</h2>
                <p>
                  Create access for an exact Google account email. No email is
                  sent automatically. Share the sign-in instructions; the
                  recipient can select Continue with Google without entering a
                  code. Tailscale invitations are separate from application
                  access.
                </p>
                <form
                  method="post"
                  onSubmit={(e) => {
                    const f = form(e);
                    void operate("administration/invitations", {
                      email: f.get("email"),
                      roles: f.getAll("roles"),
                      hours: Number(f.get("hours")),
                    });
                  }}
                >
                  <label>
                    Google account email
                    <input
                      className="form-control"
                      name="email"
                      type="email"
                      required
                      maxLength={320}
                    />
                  </label>
                  <RoleChoices selected={["member"]} />
                  <label>
                    Valid hours
                    <input
                      className="form-control"
                      name="hours"
                      type="number"
                      min={1}
                      max={168}
                      defaultValue={24}
                      required
                    />
                  </label>
                  <button className="btn btn-primary action" disabled={busy}>
                    Create invitation
                  </button>
                </form>
                {invited && (
                  <div role="status">
                    <p>
                      Invitation created for {invited.email}. Email delivery is
                      manual.
                    </p>
                    <InvitationDelivery invitation={invited} />
                  </div>
                )}
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
                        label: "Delivery",
                        cell: (i) =>
                          !i.revoked &&
                          !i.used_by &&
                          new Date(i.expires_at) > new Date() ? (
                            <InvitationDelivery invitation={i} />
                          ) : (
                            "Unavailable"
                          ),
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
              <section
                role="tabpanel"
                aria-label="Users"
                hidden={tab !== "Users"}
                className="card panel"
              >
                <h2>Users</h2>
                <p>
                  Google-linked application identities. Existing local
                  identities require explicit offline linking; ownership and
                  history are preserved.
                </p>
                {accounts === null ? (
                  <p>Loading users…</p>
                ) : accounts.length === 0 ? (
                  <p>No linked users.</p>
                ) : (
                  accounts.map((account) => (
                    <form
                      method="post"
                      className="card panel"
                      key={
                        account.id +
                        account.roles.join() +
                        String(account.enabled)
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
                      <h3>
                        <Avatar
                          name={account.display_name}
                          picture={account.picture}
                        />{" "}
                        {account.display_name}
                      </h3>
                      <p>
                        {account.email} · {account.id}
                      </p>
                      <RoleChoices selected={account.roles} />
                      <label>
                        <input
                          className="form-check-input"
                          type="checkbox"
                          name="enabled"
                          defaultChecked={account.enabled}
                        />{" "}
                        Account enabled
                      </label>
                      <button
                        className="btn btn-primary action"
                        disabled={busy}
                      >
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
              <section
                role="tabpanel"
                aria-label="Audit"
                hidden={tab !== "Audit"}
                className="card panel"
              >
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
                        cell: (e) => (
                          <>
                            {e.actor_id ? (
                              <UserName
                                id={e.actor_id}
                                name={e.actor_name}
                                picture={e.actor_picture}
                              />
                            ) : (
                              "Unauthenticated"
                            )}
                            <small>{e.action}</small>
                          </>
                        ),
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
            </>
          )}
          {page && !loading && (
            <Pager
              offset={offset}
              limit={page.limit}
              total={page.total}
              onChange={setOffset}
            />
          )}
        </div>
      </main>
    </ApplicationShell>
  );
}

export function RoleChoices({ selected }: { selected: string[] }) {
  return (
    <fieldset className="role-choices">
      <legend>Platform roles</legend>
      {["platform_admin", "contributor", "member"].map((role) => (
        <label key={role}>
          <input
            className="form-check-input"
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

export function AccountPicker({
  platform,
  members,
  onChange,
}: {
  platform: boolean;
  members: Membership["members"];
  onChange?: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const path = `administration/users?paged=true&offset=${offset}&search=${encodeURIComponent(search)}`;
  const [record, setRecord] = useState<{
    path: string;
    data: Page<Account>;
  } | null>(null);
  const [failure, setFailure] = useState<{
    path: string;
    error: string;
  } | null>(null);
  const page = record?.path === path ? record.data : null;
  const error = failure?.path === path ? failure.error : "";
  const loading = platform && !page && !error;
  const [selected, setSelected] = useState<{
    id: string;
    email: string;
  } | null>(null);
  useEffect(() => {
    if (!platform) return;
    let active = true;
    void call<Page<Account>>(path)
      .then((data) => {
        if (active) {
          setRecord({ path, data });
          setFailure(null);
        }
      })
      .catch((e) => {
        if (active) {
          setFailure({ path, error: e.message });
        }
      });
    return () => {
      active = false;
    };
  }, [platform, path]);
  const options = platform
    ? page?.items || []
    : members.map((m) => ({
        id: m.user_id,
        email: `Existing member ${m.user_id.slice(0, 8)}`,
      }));
  return (
    <span className="account-picker">
      {platform && (
        <input
          className="form-control"
          type="search"
          aria-label="Search invited accounts"
          placeholder="Search by name or email"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
      )}
      {platform && page && (
        <Pager
          offset={offset}
          limit={page.limit}
          total={page.total}
          onChange={setOffset}
        />
      )}
      <select
        className="form-select"
        name="user_id"
        required
        aria-label="Invited account"
        disabled={loading}
        value={selected?.id || ""}
        onChange={(e) => {
          setSelected(options.find((a) => a.id === e.target.value) || null);
          onChange?.(e.target.value);
        }}
      >
        <option value="">Select an account</option>
        {selected && !options.some((a) => a.id === selected.id) && (
          <option value={selected.id}>{selected.email} (selected)</option>
        )}
        {options.map((a) => (
          <option key={a.id} value={a.id}>
            {a.email}
          </option>
        ))}
      </select>
      {loading && <span role="status">Loading accounts…</span>}
      {error && <span role="alert">{error}</span>}
      {platform && page && (
        <Pager
          offset={offset}
          limit={page.limit}
          total={page.total}
          onChange={setOffset}
        />
      )}
    </span>
  );
}

interface MemberAccess {
  user_id: string;
  role: "owner" | "admin" | "member" | "none";
  account: Account | null;
}

export function PermissionEditor({
  workspace,
  platform,
  members,
  onUpdated,
}: {
  workspace: string;
  platform: boolean;
  members: Membership["members"];
  onUpdated: () => Promise<void>;
}) {
  const [selected, setSelected] = useState("");
  const [record, setRecord] = useState<{
    path: string;
    data: MemberAccess;
  } | null>(null);
  const [failure, setFailure] = useState<{
    path: string;
    message: string;
  } | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const path = `administration/workspaces/${workspace}/members/${selected}?revision=${revision}`;
  const access = record?.path === path ? record.data : null;
  const error = failure?.path === path ? failure.message : "";
  useEffect(() => {
    if (!selected) return;
    let active = true;
    void call<MemberAccess>(path)
      .then((data) => {
        if (active) {
          setRecord({ path, data });
          setFailure(null);
        }
      })
      .catch((e) => {
        if (active) setFailure({ path, message: e.message });
      });
    return () => {
      active = false;
    };
  }, [selected, path]);
  async function save(endpoint: string, body: unknown) {
    setBusy(true);
    setMessage("");
    setFailure(null);
    try {
      await call(endpoint, body);
      setMessage("Permissions saved.");
      setRevision((r) => r + 1);
      await onUpdated();
    } catch (e) {
      setFailure({
        path,
        message: e instanceof Error ? e.message : "Update failed.",
      });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Selected user permissions">
      <h3>User access</h3>
      <fieldset disabled={busy}>
        <legend>Select an account to view or update access</legend>
        <AccountPicker
          platform={platform}
          members={members}
          onChange={(id) => {
            setSelected(id);
            setMessage("");
          }}
        />
      </fieldset>
      {selected && !access && !error && (
        <p role="status">Loading current role and permissions...</p>
      )}
      {error && (
        <p role="alert">
          {error}{" "}
          <button
            className="btn btn-outline-primary"
            type="button"
            onClick={() => setRevision((r) => r + 1)}
          >
            Retry loading
          </button>
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {access && (
        <>
          <p>
            Current workspace access:{" "}
            {access.role === "none"
              ? "No access"
              : access.role === "owner"
                ? "Owner (inherent access)"
                : access.role === "admin"
                  ? "Workspace administrator"
                  : "Member"}
          </p>
          <form
            key={`${path}:${access.role}`}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              if (window.confirm("Save this user's workspace access?"))
                void save(`administration/workspaces/${workspace}/members`, {
                  user_id: selected,
                  role: f.get("role"),
                });
            }}
          >
            <label>
              Workspace role
              <select
                className="form-select"
                name="role"
                defaultValue={access.role === "none" ? "member" : access.role}
                disabled={busy || access.role === "owner"}
              >
                {access.role === "owner" && (
                  <option value="owner">Owner</option>
                )}
                <option value="member">Member</option>
                <option value="admin">Workspace administrator</option>
                <option value="remove">Remove access</option>
              </select>
            </label>
            <button
              className="btn btn-primary action"
              disabled={busy || access.role === "owner"}
            >
              {access.role === "none"
                ? "Add workspace access"
                : "Save workspace access"}
            </button>
          </form>
          {platform && access.account && (
            <form
              key={`${path}:platform`}
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                if (
                  window.confirm(
                    "Save platform roles and account status? This revokes the user's application sessions.",
                  )
                )
                  void save(`administration/users/${selected}`, {
                    roles: f.getAll("roles"),
                    enabled: f.has("enabled"),
                  });
              }}
            >
              <h3>Platform access - {access.account.display_name}</h3>
              <p>{access.account.email}</p>
              <fieldset disabled={busy}>
                <legend>Saved platform access</legend>
                <RoleChoices selected={access.account.roles} />
                <label>
                  <input
                    className="form-check-input"
                    name="enabled"
                    type="checkbox"
                    defaultChecked={access.account.enabled}
                  />{" "}
                  Account enabled
                </label>
              </fieldset>
              <p>
                Current permissions:{" "}
                {access.account.permissions.join(", ") || "None"}
              </p>
              <button className="btn btn-primary action" disabled={busy}>
                Save platform access and revoke sessions
              </button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
