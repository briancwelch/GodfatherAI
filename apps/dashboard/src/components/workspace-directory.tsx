"use client";

import { useEffect, useState } from "react";
import { control } from "../lib/control-client";
import type { Snapshot } from "../lib/contracts";
import { ApplicationShell } from "./application-shell";
import { Pager } from "./operational";

export function CreateWorkspace() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <details className="panel workspace-create">
      <summary>Create workspace</summary>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          setBusy(true);
          setError("");
          try {
            const workspace = await control<{ id: string }>(
              "administration/workspaces",
              { name: form.get("name") },
            );
            window.location.assign(`/workspaces/${workspace.id}`);
          } catch (e) {
            setError(
              e instanceof Error
                ? e.message
                : "Workspace creation not confirmed",
            );
            setBusy(false);
          }
        }}
      >
        <label>
          Workspace name
          <input name="name" required maxLength={200} />
        </label>
        <button className="action" disabled={busy}>
          {busy ? "Creating…" : "Create workspace"}
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </details>
  );
}

export function WorkspaceList({
  data,
  preview = false,
}: {
  data: Snapshot;
  preview?: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const rows = data.workspaces.filter((w) =>
    w.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <section className="panel">
      <h2>
        Your workspaces <span className="badge">{data.workspaces.length}</span>
      </h2>
      <p>Private and shared workspaces you can access.</p>
      {!preview && (
        <label>
          Find workspace
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setOffset(0);
            }}
          />
        </label>
      )}
      <div className="workspace-directory">
        {rows
          .slice(preview ? 0 : offset, preview ? 6 : offset + 25)
          .map((w) => (
            <a
              className="workspace-entry"
              href={`/workspaces/${w.id}`}
              key={w.id}
            >
              <strong>{w.name}</strong>
              <small>
                {w.can_manage ? "Manage workspace" : "Workspace member"} → Open
                overview
              </small>
            </a>
          ))}
      </div>
      {preview ? (
        <a href="/workspaces">View all workspaces</a>
      ) : (
        <Pager
          offset={offset}
          limit={25}
          total={rows.length}
          onChange={setOffset}
        />
      )}
      {!data.workspaces.length && (
        <p>Create your first workspace to get started.</p>
      )}
    </section>
  );
}

export default function WorkspaceDirectory({
  user,
}: {
  user: { display_name: string; roles: string[] };
}) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    void control<Snapshot>("command-center")
      .then((value) => {
        if (active) {
          setData(value);
          setError("");
        }
      })
      .catch((e: unknown) => {
        if (active)
          setError(e instanceof Error ? e.message : "Workspaces unavailable");
      });
    return () => {
      active = false;
    };
  }, [revision]);
  return (
    <ApplicationShell
      section="workspaces"
      account={user}
      data={data}
      stale={!!error}
      refresh={() => setRevision((v) => v + 1)}
    >
      <main id="main-content">
        <h1>Workspaces</h1>
        <p>The home for your agents, jobs and results.</p>
        <CreateWorkspace />
        {error && <p role="alert">{error}</p>}
        {data ? (
          <WorkspaceList data={data} />
        ) : (
          <p role="status">Loading authorized workspaces…</p>
        )}
      </main>
    </ApplicationShell>
  );
}
