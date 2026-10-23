"use client";

import { useFeedback } from "./toast-notifications";

import { useEffect, useRef, useState } from "react";
import { control } from "../lib/control-client";
import type { JobInfo, ModelInfo } from "../lib/contracts";
import { ModelAvailability, UseModel } from "./model-use";

interface InstallOptions {
  nodes: {
    node_id: string;
    name: string;
    os: string;
    available: boolean;
    providers: string[];
    installed_models: { identifier: string; provider_id: string }[];
    reason: string;
    runtime_setup?: boolean;
    runtime_ready?: boolean;
  }[];
  catalog: { identifier: string; name: string; url: string }[];
  models: ModelInfo[];
}

export function ModelInstaller({ workspace }: { workspace: string | null }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [options, setOptions] = useState<InstallOptions | null>(null);
  const [nodeId, setNodeId] = useState("");
  const [error, setError] = useState("");
  useFeedback(error);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"available" | "download">("available");
  const [provider, setProvider] = useState("");
  const [search, setSearch] = useState("");
  const [identifier, setIdentifier] = useState("");
  const node = options?.nodes.find((n) => n.node_id === nodeId);
  const installed = (id: string) =>
    node?.installed_models?.some(
      (m) => m.identifier === id && m.provider_id === provider,
    );
  async function open() {
    setError("");
    setOptions(null);
    setNodeId("");
    setProvider("");
    setSearch("");
    setIdentifier("");
    setTab("available");
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
          className="btn btn-primary action"
          disabled={!workspace}
          onClick={() => void open()}
        >
          Add / use model
        </button>
        <span className="muted">
          Use installed local models or your connected API models, or download a
          new local model.
        </span>
      </div>
      <dialog
        ref={dialog}
        className="agent-dialog"
        aria-label="Add or use a model"
        onCancel={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (tab !== "download") return;
            if (installed(identifier)) {
              setTab("available");
              setSearch(identifier);
              return;
            }
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
                install_runtime: form.get("install_runtime") === "on",
              });
              window.location.assign(`/jobs/${job.id}`);
            } catch (e) {
              if (e instanceof Error && /already installed/i.test(e.message)) {
                try {
                  setOptions(
                    await control<InstallOptions>(
                      `models/install-options?workspace_id=${workspace}`,
                    ),
                  );
                  setSearch(identifier);
                  setTab("available");
                  setBusy(false);
                  return;
                } catch {
                  /* Preserve the request error if inventory refresh also fails. */
                }
              }
              setError(
                e instanceof Error
                  ? e.message
                  : "Installation request not confirmed",
              );
              setBusy(false);
            }
          }}
        >
          <h2>Add or use a model</h2>
          <div className="actions" role="group" aria-label="Model source">
            <button
              type="button"
              className="btn btn-outline-primary action secondary"
              disabled={busy}
              aria-pressed={tab === "available"}
              onClick={() => setTab("available")}
            >
              Local &amp; API models
            </button>
            <button
              type="button"
              className="btn btn-outline-primary action secondary"
              disabled={busy}
              aria-pressed={tab === "download"}
              onClick={() => setTab("download")}
            >
              Download local model
            </button>
          </div>
          {!options && !error && (
            <p role="status">Loading owned workers and model catalog…</p>
          )}
          {options && tab === "available" && (
            <>
              <p>
                Select an installed local model or a model from your connected
                API account. Workspace access and worker status are shown
                separately. Selecting a model does not run inference or download
                anything.
              </p>
              <label>
                Find a model
                <input
                  className="form-control"
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Model, OpenAI, Ollama or computer name"
                />
              </label>
              <div style={{ maxHeight: "50vh", overflow: "auto" }}>
                {options.models
                  .filter((m) =>
                    `${m.deployment.identifier} ${m.deployment.provider} ${m.node_name || ""}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                  )
                  .map((m) => (
                    <section
                      className="model-choice"
                      key={`${m.node_id}:${m.deployment.provider_id}:${m.deployment.identifier}`}
                    >
                      <div>
                        <strong>{m.deployment.identifier}</strong>
                        <small>
                          {m.deployment.provider} · {m.node_name || m.node_id}
                        </small>
                        <small>
                          <ModelAvailability model={m} />
                        </small>
                      </div>
                      {workspace && (
                        <UseModel workspace={workspace} model={m} />
                      )}
                    </section>
                  ))}
              </div>
              {!options.models.length && (
                <p>
                  No discovered models. Check selected computers in{" "}
                  <a href="/providers">Account settings</a>, enable account API
                  connections in Consigliere, and connect the worker. For local
                  models, enable local models and keep Ollama running.
                </p>
              )}
              <p className="muted">
                API runs require confirmation before task data is sent. Showing
                up to 200 advertisements; the model directory has more pages.
              </p>
            </>
          )}
          {options && tab === "download" && (
            <>
              <div className="form-grid">
                <label>
                  Owned worker
                  <select
                    className="form-select"
                    required
                    aria-label="Owned worker"
                    value={nodeId}
                    onChange={(e) => {
                      setNodeId(e.target.value);
                      setProvider(
                        options.nodes.find((n) => n.node_id === e.target.value)
                          ?.providers[0] || "",
                      );
                      setIdentifier("");
                    }}
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
                    className="form-select"
                    key={nodeId}
                    name="provider"
                    aria-label="Ollama runtime"
                    required
                    disabled={!node}
                    value={provider}
                    onChange={(e) => {
                      setProvider(e.target.value);
                      setIdentifier("");
                    }}
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
              {node?.runtime_setup && (
                <label key={nodeId} className="check-label">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    name="install_runtime"
                    defaultChecked={true}
                  />{" "}
                  Install or start Ollama on this worker if needed. The worker
                  owner has enabled local runtime setup; verified files use this
                  computer’s network and storage.
                </label>
              )}
              {node && !node.runtime_ready && !node.runtime_setup && (
                <p className="alert alert-warning notice">
                  Ollama may need setup. On this computer open Consigliere →
                  Models &amp; API connections → Get started to approve local
                  runtime installation.
                </p>
              )}
              {!options.nodes.some((n) => n.available) && (
                <p className="alert alert-warning notice">
                  No eligible owned worker. In Consigliere, select Pause, then
                  Models &amp; API connections. Enable both Allow my existing
                  local AI models and Allow model downloads from Command Center,
                  then Resume. If Ollama is missing, use Get started in the
                  worker to approve runtime setup. Reopen this dialog after the
                  worker connects. Update Consigliere if the download option is
                  missing.
                </p>
              )}
              <fieldset className="model-catalog">
                <legend>Select a model</legend>
                {options.catalog.map((m) => (
                  <label className="model-choice" key={m.identifier}>
                    <input
                      className="form-check-input"
                      type="radio"
                      name="identifier"
                      value={m.identifier}
                      disabled={!!installed(m.identifier)}
                      checked={identifier === m.identifier}
                      onChange={() => setIdentifier(m.identifier)}
                      required
                    />
                    <span>
                      <strong>{m.name}</strong>
                      <small>
                        {m.identifier}
                        {installed(m.identifier) ? " · Already installed" : ""}
                      </small>
                    </span>
                    {installed(m.identifier) ? (
                      <button
                        type="button"
                        className="btn btn-outline-primary action secondary"
                        onClick={() => {
                          setSearch(m.identifier);
                          setTab("available");
                        }}
                      >
                        Use installed model
                      </button>
                    ) : (
                      <a href={m.url} target="_blank" rel="noreferrer">
                        Details / license
                      </a>
                    )}
                  </label>
                ))}
              </fieldset>
              <p>
                Downloads use this worker’s network and storage. No cloud
                inference is enabled. A cancelled or failed pull may leave
                cached files; no installed model is deleted.
              </p>
              <label className="check-label">
                <input
                  className="form-check-input"
                  type="checkbox"
                  name="confirm"
                  required
                />
                I authorize downloading the selected model onto my selected
                worker.
              </label>
            </>
          )}
          {error && (
            <p role="alert" className="alert alert-danger notice error">
              {error}
            </p>
          )}
          <div className="actions">
            <button
              type="button"
              className="btn btn-outline-primary action secondary"
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            {tab === "download" && (
              <button
                className="btn btn-primary action"
                disabled={
                  busy ||
                  !node?.available ||
                  !identifier ||
                  !!installed(identifier)
                }
              >
                {busy ? "Queuing installation…" : "Install selected model"}
              </button>
            )}
          </div>
        </form>
      </dialog>
    </>
  );
}
