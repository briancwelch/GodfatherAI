"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApplicationShell, RibbonGroup } from "./application-shell";
import { notifyError } from "../lib/notifications";
import { control } from "../lib/control-client";
import type { Snapshot } from "../lib/contracts";
import { CommandIcon } from "./command-icon";
import { StatusBadge } from "./operational";

interface Options {
  cloud_image_models?: {
    node_id: string;
    node_name: string;
    available: boolean;
    provider: "openai" | "gemini";
    model: string;
    connection_id: string;
  }[];
  nodes: {
    id: string;
    name: string;
    available: boolean;
    analytics: boolean;
    image_models: string[];
    cloud_image_models?: string[];
  }[];
  sql_note: string;
}

export function WorkerAvailabilityList({
  nodes,
  workflow,
}: {
  nodes: Options["nodes"];
  workflow: "images" | "analytics";
}) {
  return (
    <ul className="worker-availability-list" aria-label="Worker availability">
      {nodes.map((node) => (
        <li key={node.id} className="worker-availability-row">
          <div className="worker-availability-heading">
            <strong>{node.name}</strong>
            <StatusBadge value={node.available ? "Online" : "Unavailable"} />
          </div>
          <div className="worker-capabilities">
            {workflow === "images" ? (
              node.image_models.length || node.cloud_image_models?.length ? (
                [...node.image_models, ...(node.cloud_image_models ?? [])].map(
                  (model) => (
                    <span className="status worker-capability" key={model}>
                      Image model: {model}
                    </span>
                  ),
                )
              ) : (
                <span className="status status-warning">No image models</span>
              )
            ) : (
              <span
                className={`status ${node.analytics ? "status-available" : "status-warning"}`}
              >
                {node.analytics
                  ? "Analytics configured"
                  : "Analytics unavailable"}
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function Workloads({
  user,
  workflow = "analytics",
}: {
  user: { id: string; display_name: string; roles: string[] };
  workflow?: "images" | "analytics";
}) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [workspace, setWorkspace] = useState("");
  const [options, setOptions] = useState<Options | null>(null);
  const [kind, setKind] = useState(workflow === "images" ? "image" : "report");
  const [backend, setBackend] = useState("automatic1111");
  const [setupOpen, setSetupOpen] = useState(true);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    void control<Snapshot>(
      "command-center?section=jobs" +
        (workspace ? `&workspace_id=${workspace}` : ""),
    )
      .then(async (snapshot) => {
        const selected =
          workspace || snapshot.workspace_id || snapshot.workspaces[0]?.id;
        const available = selected
          ? await control<Options>(`workloads/options?workspace_id=${selected}`)
          : null;
        if (active) {
          setData(snapshot);
          setOptions(available);
        }
      })
      .catch((e: unknown) => {
        if (active)
          setStatus(e instanceof Error ? e.message : "Workloads unavailable");
      });
    return () => {
      active = false;
    };
  }, [workspace, revision]);
  const models = [
    ...new Set(
      options?.nodes
        .filter((n) => n.available)
        .flatMap((n) => n.image_models) || [],
    ),
  ];
  const available =
    kind === "image"
      ? backend === "automatic1111"
        ? models.length > 0
        : !!options?.cloud_image_models?.some(
            (m) => m.available && m.provider === backend,
          )
      : !!options?.nodes.some((n) => n.available && n.analytics);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const workspaceId =
      workspace || data?.workspace_id || data?.workspaces[0]?.id;
    if (!workspaceId) return;
    setBusy(true);
    setStatus("Validating upload and submitting…");
    try {
      let dataset;
      const file = form.get("dataset");
      if (kind !== "image") {
        if (
          !(file instanceof File) ||
          file.size === 0 ||
          file.size > 1048576 ||
          !/\.(csv|json|xlsx)$/.test(file.name)
        )
          throw new Error("Choose a CSV, JSON or XLSX file up to 1 MiB.");
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = "";
        for (const byte of bytes) binary += String.fromCharCode(byte);
        dataset = { filename: file.name, content_base64: btoa(binary) };
      }
      const result = await control<{ id: string }>("workloads/jobs", {
        workspace_id: workspaceId,
        kind,
        ...(kind === "image" && backend !== "automatic1111"
          ? {
              connection_id: String(form.get("model")).split("|")[0],
              paid_consent: form.get("paid_consent") === "on",
            }
          : {}),
        ram_bytes: Number(form.get("memory_mb") || 512) * 1024 ** 2,
        gpu_memory_bytes: Number(form.get("vram_mb") || 0) * 1024 ** 2,
        input: {
          instruction: String(form.get("instruction")),
          ...(dataset
            ? {
                dataset,
                analysis: {
                  group_by: form.get("group_by") || null,
                  date_column: form.get("date_column") || null,
                  value_column: form.get("value_column") || null,
                },
                report_format: form.get("report_format") || "html",
              }
            : {}),
          ...(kind === "image"
            ? {
                image: {
                  backend,
                  model:
                    backend === "automatic1111"
                      ? form.get("model")
                      : String(form.get("model")).split("|")[1],
                  width:
                    backend === "automatic1111"
                      ? Number(form.get("width"))
                      : 1024,
                  height:
                    backend === "automatic1111"
                      ? Number(form.get("height"))
                      : 1024,
                  count:
                    backend === "automatic1111" ? Number(form.get("count")) : 1,
                  steps:
                    backend === "automatic1111"
                      ? Number(form.get("steps"))
                      : 20,
                  seed:
                    backend === "automatic1111" ? Number(form.get("seed")) : -1,
                },
              }
            : {}),
        },
      });
      window.location.assign(`/jobs/${result.id}`);
    } catch (error) {
      notifyError(error instanceof Error ? error.message : "Submission failed");
      setStatus(error instanceof Error ? error.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <ApplicationShell
      section={workflow}
      data={data}
      account={user}
      refresh={() => setRevision((v) => v + 1)}
      ribbon={
        <RibbonGroup label="Workloads">
          <a className="btn btn-outline-primary action secondary" href="/jobs">
            Job history
          </a>
          <a className="btn btn-outline-primary action secondary" href="/nodes">
            Worker computers
          </a>
        </RibbonGroup>
      }
    >
      <main
        id="main-content"
        className={
          "container-fluid " +
          `workload-layout ${setupOpen ? "" : "setup-collapsed"}`
        }
      >
        <section className="card panel">
          <h1>{workflow === "images" ? "Images" : "Analytics and Reports"}</h1>
          <p>
            {workflow === "images"
              ? "Generate images with a permitted local model or your cloud API connection."
              : "Analyze authorized data and create reproducible reports on a compatible worker."}
          </p>
          <p role="status" aria-live="polite">
            {status}
          </p>
          {!data ? (
            <p>Loading workspaces and worker capabilities…</p>
          ) : !data.workspaces.length ? (
            <p>No authorized workspace is available.</p>
          ) : (
            <form onSubmit={(e) => void submit(e)} className="workload-form">
              <label>
                Workspace
                <select
                  className="form-select"
                  value={
                    workspace || data.workspace_id || data.workspaces[0]?.id
                  }
                  onChange={(e) => {
                    setWorkspace(e.target.value);
                    setOptions(null);
                  }}
                >
                  {data.workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              {workflow === "analytics" && (
                <label>
                  Workflow
                  <select
                    className="form-select"
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    <option value="report">Analytics → report</option>
                    <option value="analytics">Analytics only</option>
                  </select>
                </label>
              )}
              {!available && (
                <p className="alert alert-warning notice">
                  {kind === "image"
                    ? "Image generation unavailable: no permitted online worker advertises a configured local image model. No paid fallback is used."
                    : "No opted-in analytics worker is online. Connect a worker with a preinstalled Python sandbox image and explicit data-analysis permission."}{" "}
                  <button
                    type="button"
                    className="btn btn-outline-primary action secondary"
                    onClick={() => setSetupOpen(true)}
                  >
                    Show worker setup
                  </button>
                </p>
              )}
              <label>
                {kind === "image"
                  ? "Image prompt"
                  : "Analysis request / report context"}
                <textarea
                  className="form-control"
                  name="instruction"
                  required
                  maxLength={4096}
                  rows={3}
                />
              </label>
              {kind === "image" ? (
                <>
                  <label>
                    Provider
                    <select
                      className="form-select"
                      name="backend"
                      value={backend}
                      onChange={(e) => setBackend(e.target.value)}
                    >
                      <option value="automatic1111">
                        AUTOMATIC1111 (local)
                      </option>
                      <option value="openai">OpenAI (provider billing)</option>
                      <option value="gemini">
                        Google Gemini (provider billing)
                      </option>
                    </select>
                  </label>
                  <label>
                    {backend === "automatic1111"
                      ? "Installed model"
                      : "My cloud model and computer"}
                    <select
                      className="form-select"
                      name="model"
                      required
                      key={backend + workspace}
                    >
                      <option value="">Select a model</option>
                      {backend === "automatic1111"
                        ? models.map((m) => <option key={m}>{m}</option>)
                        : options?.cloud_image_models
                            ?.filter(
                              (m) => m.available && m.provider === backend,
                            )
                            .map((m) => (
                              <option
                                key={`${m.connection_id}|${m.model}`}
                                value={`${m.connection_id}|${m.model}`}
                              >
                                {m.model} · {m.node_name}
                              </option>
                            ))}
                    </select>
                  </label>
                  {backend !== "automatic1111" && (
                    <>
                      <p>
                        One 1024 × 1024 PNG per job. Your provider controls
                        billing and model access.
                      </p>
                      <label className="check-label" key={backend}>
                        <input
                          className="form-check-input"
                          type="checkbox"
                          name="paid_consent"
                          required
                        />{" "}
                        I authorize sending this prompt to{" "}
                        {backend === "openai" ? "OpenAI" : "Google Gemini"}{" "}
                        using my selected API connection and accept provider
                        charges.
                      </label>
                    </>
                  )}
                  {backend === "automatic1111" && (
                    <div className="workload-fields">
                      {["width", "height"].map((name) => (
                        <label key={name}>
                          {name === "width" ? "Width" : "Height"}
                          <select
                            className="form-select"
                            name={name}
                            defaultValue="512"
                          >
                            {[256, 512, 768, 1024].map((n) => (
                              <option key={n}>{n}</option>
                            ))}
                          </select>
                        </label>
                      ))}
                      <label>
                        Images
                        <input
                          className="form-control"
                          name="count"
                          type="number"
                          min="1"
                          max="4"
                          defaultValue="1"
                        />
                      </label>
                      <label>
                        Quality (sampling steps)
                        <input
                          className="form-control"
                          name="steps"
                          type="number"
                          min="1"
                          max="50"
                          defaultValue="20"
                        />
                      </label>
                      <label>
                        Seed (-1: random)
                        <input
                          className="form-control"
                          name="seed"
                          type="number"
                          min="-1"
                          max="4294967295"
                          defaultValue="-1"
                        />
                      </label>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <label>
                    Authorized dataset
                    <input
                      className="form-control"
                      name="dataset"
                      type="file"
                      accept=".csv,.json,.xlsx"
                      required
                    />
                  </label>
                  <p className="muted">
                    Up to 1 MiB, 10,000 rows and 64 columns. CSV/JSON use flat
                    records; Excel uses a values-only first worksheet. SQL
                    results may be exported as JSON. The selected workspace and
                    permitted worker owners can access this data.
                  </p>
                  <div className="workload-fields">
                    <label>
                      Group by column
                      <input
                        className="form-control"
                        name="group_by"
                        maxLength={120}
                      />
                    </label>
                    <label>
                      ISO date column
                      <input
                        className="form-control"
                        name="date_column"
                        maxLength={120}
                      />
                    </label>
                    <label>
                      Value column (blank: count)
                      <input
                        className="form-control"
                        name="value_column"
                        maxLength={120}
                      />
                    </label>
                  </div>
                  {kind === "report" && (
                    <label>
                      Report format
                      <select className="form-select" name="report_format">
                        <option value="html">HTML with chart</option>
                        <option value="markdown">Markdown</option>
                        <option value="csv">CSV</option>
                        <option value="xlsx">Excel</option>
                      </select>
                    </label>
                  )}
                  <p>{options?.sql_note}</p>
                </>
              )}
              <details>
                <summary>Resource requirements</summary>
                <div className="workload-fields">
                  <label>
                    Minimum memory (MiB)
                    <input
                      className="form-control"
                      type="number"
                      name="memory_mb"
                      min="512"
                      max="1048576"
                      defaultValue="512"
                    />
                  </label>
                  <label>
                    Minimum GPU memory (MiB)
                    <input
                      className="form-control"
                      type="number"
                      name="vram_mb"
                      min="0"
                      max="1048576"
                      defaultValue="0"
                    />
                  </label>
                </div>
                <p>
                  Execution queues if these requirements are unavailable.
                  Analytics/report execution is limited to one CPU and 512 MiB
                  per stage.
                </p>
              </details>
              <label className="check-label">
                <input className="form-check-input" type="checkbox" required />{" "}
                I authorize processing this data or prompt on a worker permitted
                by this workspace and its owner.
              </label>
              <button
                className="btn btn-primary action"
                type="submit"
                disabled={busy || !available}
              >
                {busy ? "Submitting…" : "Run workload"}
              </button>
            </form>
          )}
        </section>
        <aside
          className="card panel worker-readiness"
          id="workload-setup"
          aria-label="Worker setup and availability"
        >
          <button
            className="readiness-toggle"
            aria-expanded={setupOpen}
            aria-controls="readiness-content"
            onClick={() => setSetupOpen(!setupOpen)}
            title={setupOpen ? "Collapse worker setup" : "Expand worker setup"}
          >
            <CommandIcon
              label={
                setupOpen ? "Collapse worker setup" : "Expand worker setup"
              }
            />
            <span>Worker setup and availability</span>
          </button>
          <div id="readiness-content" hidden={!setupOpen}>
            <h2>
              {!data
                ? "Checking worker readiness"
                : available
                  ? "Ready to process"
                  : "Get your worker ready"}
            </h2>
            <span
              className={`badge ${data && !available ? "worker-outdated" : ""}`}
            >
              {!data
                ? "Waiting for backend state"
                : !data.workspaces.length
                  ? "Create or select a workspace"
                  : available
                    ? "Compatible worker online"
                    : "Setup required"}
            </span>
            {workflow === "analytics" && (
              <>
                <p>
                  Data execution requires an owner-configured, already installed
                  Python container image pinned by digest, plus local Docker.
                  The worker isolates uploaded data without network or host
                  workspace access. No image or model downloads are automatic.
                </p>
              </>
            )}
            {workflow === "images" && (
              <>
                <p>
                  Local images require a configured AUTOMATIC1111 API and
                  permitted model. For cloud images, add your OpenAI or Gemini
                  key in AI connections, select your own computer, and enable
                  account API connections plus cloud image generation in
                  Consigliere Settings. Reconnect an existing provider key to
                  refresh its supported image catalog.
                </p>
              </>
            )}
            <p>
              Update Consigliere, Pause the worker, then open Settings to enable
              {workflow === "images"
                ? " a local image connection or cloud image generation."
                : " data processing."}{" "}
              Resume after saving.
              {workflow === "analytics" &&
                " Google account file connections are unavailable in this version; export your authorized spreadsheet and upload it above."}
            </p>
            {workflow === "images" && (
              <a href="/providers">Open AI connections</a>
            )}
            {options && (
              <WorkerAvailabilityList
                nodes={options.nodes}
                workflow={workflow}
              />
            )}
            <a
              className="btn btn-primary action readiness-action"
              href="/nodes"
            >
              Connect or inspect a worker
            </a>
          </div>
        </aside>
      </main>
    </ApplicationShell>
  );
}
