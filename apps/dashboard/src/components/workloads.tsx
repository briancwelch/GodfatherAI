"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApplicationShell, RibbonGroup } from "./application-shell";
import { control } from "../lib/control-client";
import type { Snapshot } from "../lib/contracts";

interface Options {
  nodes: {
    id: string;
    name: string;
    available: boolean;
    analytics: boolean;
    image_models: string[];
  }[];
  sql_note: string;
}

export default function Workloads({
  user,
}: {
  user: { id: string; display_name: string; roles: string[] };
}) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [workspace, setWorkspace] = useState("");
  const [options, setOptions] = useState<Options | null>(null);
  const [kind, setKind] = useState("report");
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
      ? models.length > 0
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
                  backend: "automatic1111",
                  model: form.get("model"),
                  width: Number(form.get("width")),
                  height: Number(form.get("height")),
                  count: Number(form.get("count")),
                  steps: Number(form.get("steps")),
                  seed: Number(form.get("seed")),
                },
              }
            : {}),
        },
      });
      window.location.assign(`/jobs/${result.id}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <ApplicationShell
      section="workloads"
      data={data}
      account={user}
      refresh={() => setRevision((v) => v + 1)}
      ribbon={
        <RibbonGroup label="Workloads">
          <a className="action secondary" href="/jobs">
            Job history
          </a>
          <a className="action secondary" href="/nodes">
            Worker computers
          </a>
        </RibbonGroup>
      }
    >
      <section className="panel">
        <h1>Images, analytics and reports</h1>
        <p>
          Upload authorized data, choose the calculation columns, and receive
          persisted results from a compatible worker.
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
                value={workspace || data.workspace_id || data.workspaces[0]?.id}
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
            <label>
              Workload
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="report">Analytics → report</option>
                <option value="analytics">Analytics only</option>
                <option value="image">Generate images</option>
              </select>
            </label>
            {!available && (
              <p className="notice">
                {kind === "image"
                  ? "Image generation unavailable: no permitted online worker advertises a configured local image model. No paid fallback is used."
                  : "No opted-in analytics worker is online. Connect a worker with a preinstalled Python sandbox image and explicit data-analysis permission."}{" "}
                <a href="#workload-setup">Setup details</a>
              </p>
            )}
            <label>
              {kind === "image"
                ? "Image prompt"
                : "Analysis request / report context"}
              <textarea name="instruction" required maxLength={4096} rows={3} />
            </label>
            {kind === "image" ? (
              <>
                <label>
                  Provider
                  <select name="backend">
                    <option>AUTOMATIC1111 (local)</option>
                  </select>
                </label>
                <label>
                  Installed model
                  <select name="model" required>
                    {models.map((m) => (
                      <option key={m}>{m}</option>
                    ))}
                  </select>
                </label>
                <div className="workload-fields">
                  {["width", "height"].map((name) => (
                    <label key={name}>
                      {name === "width" ? "Width" : "Height"}
                      <select name={name} defaultValue="512">
                        {[256, 512, 768, 1024].map((n) => (
                          <option key={n}>{n}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                  <label>
                    Images
                    <input
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
                      name="seed"
                      type="number"
                      min="-1"
                      max="4294967295"
                      defaultValue="-1"
                    />
                  </label>
                </div>
              </>
            ) : (
              <>
                <label>
                  Authorized dataset
                  <input
                    name="dataset"
                    type="file"
                    accept=".csv,.json,.xlsx"
                    required
                  />
                </label>
                <p className="muted">
                  Up to 1 MiB, 10,000 rows and 64 columns. CSV/JSON use flat
                  records; Excel uses a values-only first worksheet. SQL results
                  may be exported as JSON. The selected workspace and permitted
                  worker owners can access this data.
                </p>
                <div className="workload-fields">
                  <label>
                    Group by column
                    <input name="group_by" maxLength={120} />
                  </label>
                  <label>
                    ISO date column
                    <input name="date_column" maxLength={120} />
                  </label>
                  <label>
                    Value column (blank: count)
                    <input name="value_column" maxLength={120} />
                  </label>
                </div>
                {kind === "report" && (
                  <label>
                    Report format
                    <select name="report_format">
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
                Analytics/report execution is limited to one CPU and 512 MiB per
                stage.
              </p>
            </details>
            <label className="check-label">
              <input type="checkbox" required /> I authorize processing this
              data or prompt on a worker permitted by this workspace and its
              owner.
            </label>
            <button
              className="action"
              type="submit"
              disabled={busy || !available}
            >
              {busy ? "Submitting…" : "Run workload"}
            </button>
          </form>
        )}
      </section>
      <section className="panel" id="workload-setup">
        <h2>Worker setup and availability</h2>
        <p>
          Data execution requires an owner-configured, already installed Python
          container image pinned by digest, plus local Docker. The worker
          isolates uploaded data without network or host workspace access. No
          image or model downloads are automatic.
        </p>
        <p>
          Image execution requires a locally configured AUTOMATIC1111 API and an
          installed permitted model. Cloud image providers, live SQL connections
          and PDF output are not configured in this version.
        </p>
        <p>
          Update Consigliere, Pause the worker, then open Settings to enable
          data processing or a local image connection. Resume after saving.
          Google account file connections are unavailable in this version;
          export your authorized spreadsheet and upload it above.
        </p>
        <ul>
          {options?.nodes.map((n) => (
            <li key={n.id}>
              {n.name}: {n.available ? "online" : "unavailable"};
              analytics/reporting {n.analytics ? "configured" : "unavailable"};
              image models {n.image_models.join(", ") || "none"}
            </li>
          ))}
        </ul>
      </section>
    </ApplicationShell>
  );
}
