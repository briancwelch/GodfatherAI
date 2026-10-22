"use client";

import { useEffect, useRef, useState } from "react";
import { control } from "../lib/control-client";
import type { JobInfo } from "../lib/contracts";

interface InstallOptions {
  nodes: {
    node_id: string;
    name: string;
    os: string;
    available: boolean;
    providers: string[];
    reason: string;
  }[];
  catalog: { identifier: string; name: string; url: string }[];
}

export function ModelInstaller({ workspace }: { workspace: string | null }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [options, setOptions] = useState<InstallOptions | null>(null);
  const [nodeId, setNodeId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const node = options?.nodes.find((n) => n.node_id === nodeId);
  async function open() {
    setError("");
    setOptions(null);
    setNodeId("");
    dialog.current?.showModal();
    try {
      setOptions(
        await control<InstallOptions>(
          `models/install-options?workspace_id=${workspace}`,
        ),
      );
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Installation options unavailable",
      );
    }
  }
  useEffect(() => {
    dialog.current?.close();
  }, [workspace]);
  return (
    <>
      <div className="actions model-directory-actions">
        <button
          id="model-install-launch"
          className="action"
          disabled={!workspace}
          onClick={() => void open()}
        >
          Add / install model
        </button>
        <span className="muted">
          Select a model and an owned worker. Installed models appear after
          worker discovery.
        </span>
      </div>
      <dialog
        ref={dialog}
        className="agent-dialog"
        aria-label="Install a model on an owned worker"
        onCancel={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            const form = new FormData(e.currentTarget);
            try {
              const job = await control<JobInfo>("models/install", {
                workspace_id: workspace,
                node_id: nodeId,
                provider_id: form.get("provider"),
                identifier: form.get("identifier"),
                confirm_download: form.get("confirm") === "on",
              });
              window.location.assign(`/jobs/${job.id}`);
            } catch (e) {
              setError(
                e instanceof Error
                  ? e.message
                  : "Installation request not confirmed",
              );
              setBusy(false);
            }
          }}
        >
          <h2>Add a model</h2>
          <p>
            Download catalog · models below are installation choices, not
            installed inventory.
          </p>
          {!options && !error && (
            <p role="status">Loading owned workers and model catalog…</p>
          )}
          {options && (
            <>
              <div className="form-grid">
                <label>
                  Owned worker
                  <select
                    required
                    aria-label="Owned worker"
                    value={nodeId}
                    onChange={(e) => setNodeId(e.target.value)}
                  >
                    <option value="">Select an eligible worker</option>
                    {options.nodes.map((n) => (
                      <option
                        key={n.node_id}
                        value={n.node_id}
                        disabled={!n.available}
                      >
                        {n.name} · {n.os}
                        {n.available ? "" : ` · ${n.reason}`}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Ollama runtime
                  <select
                    key={nodeId}
                    name="provider"
                    aria-label="Ollama runtime"
                    required
                    disabled={!node}
                  >
                    <option value="">Select a runtime</option>
                    {node?.providers.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {!options.nodes.some((n) => n.available) && (
                <p className="notice">
                  No eligible owned worker. In Consigliere, select Pause, then
                  Models &amp; API connections. Enable both Allow my existing
                  local AI models and Allow model downloads from Command Center,
                  then Resume. Keep Ollama running and reopen this dialog after
                  the worker connects. Update Consigliere if the download option
                  is missing.
                </p>
              )}
              <fieldset className="model-catalog">
                <legend>Select a model</legend>
                {options.catalog.map((m) => (
                  <label className="model-choice" key={m.identifier}>
                    <input
                      type="radio"
                      name="identifier"
                      value={m.identifier}
                      required
                    />
                    <span>
                      <strong>{m.name}</strong>
                      <small>{m.identifier}</small>
                    </span>
                    <a href={m.url} target="_blank" rel="noreferrer">
                      Details / license
                    </a>
                  </label>
                ))}
              </fieldset>
              <p>
                Downloads use this worker’s network and storage. No cloud
                inference is enabled. A cancelled or failed pull may leave
                cached files; no installed model is deleted.
              </p>
              <label className="check-label">
                <input type="checkbox" name="confirm" required />I authorize
                downloading the selected model onto my selected worker.
              </label>
            </>
          )}
          {error && (
            <p role="alert" className="notice error">
              {error}
            </p>
          )}
          <div className="actions">
            <button
              type="button"
              className="action secondary"
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button className="action" disabled={busy || !node?.available}>
              {busy ? "Queuing installation…" : "Install selected model"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
