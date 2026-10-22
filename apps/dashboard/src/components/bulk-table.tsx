"use client";

import { useState, type ComponentProps } from "react";
import { control } from "../lib/control-client";
import { WorkspaceDelete } from "./workspace-delete";
import { ConfirmAction, DataTable } from "./operational";

export function BulkTable<T>({
  kind,
  scope,
  deleteKey,
  label,
  eligible,
  onDeleted,
  ...table
}: ComponentProps<typeof DataTable<T>> & {
  kind: "workspaces" | "jobs" | "agents";
  scope: string;
  deleteKey: (row: T) => string;
  label: (row: T) => string;
  eligible: (row: T) => boolean;
  onDeleted: () => void | Promise<void>;
}) {
  const [selection, setSelection] = useState<{ scope: string; ids: string[] }>({
    scope,
    ids: [],
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const visible = new Set(table.rows.filter(eligible).map(deleteKey));
  const ids =
    selection.scope === scope
      ? selection.ids.filter((id) => visible.has(id))
      : [];
  async function remove() {
    setBusy(true);
    setMessage("");
    try {
      const result = await control<{ deleted_ids: string[] }>(
        "administration/bulk-delete",
        { kind, ids },
      );
      setSelection({ scope, ids: [] });
      setMessage(`Deleted ${result.deleted_ids.length} ${kind}.`);
      await onDeleted();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label={`Manage ${kind}`} aria-busy={busy}>
      <div className="actions">
        <span>{ids.length} selected on this page</span>
        {kind === "workspaces" ? (
          <WorkspaceDelete
            ids={ids}
            names={ids.map((id) =>
              label(table.rows.find((row) => deleteKey(row) === id)!),
            )}
            disabled={busy || !ids.length}
            onDelete={remove}
          />
        ) : (
          <ConfirmAction
            label="Delete selected"
            disabled={busy || !ids.length}
            description={`Delete ${ids.length} selected ${kind}? ${kind === "agents" ? "All versions of each selected agent will be removed. " : ""}${kind === "jobs" ? "Only completed, failed or cancelled jobs can be deleted. " : "Unfinished jobs must be cancelled or finished first. "}Items disappear from normal lists. Execution history, artifacts and usage records are retained. No files on worker computers are removed.`}
            onConfirm={remove}
          />
        )}
      </div>
      {message && <p role="status">{message}</p>}
      <DataTable
        {...table}
        selection={{
          ids,
          key: deleteKey,
          label,
          eligible,
          disabled: busy,
          onChange: (next) => setSelection({ scope, ids: [...new Set(next)] }),
        }}
      />
    </section>
  );
}
