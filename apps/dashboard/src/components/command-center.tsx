"use client";

import { useEffect, useState, type FormEvent } from "react";
import { GoogleLogin } from "@/components/google-login";
import { Button } from "@/components/ui/button";
import {
  ConfirmAction,
  DataTable,
  EventTimeline,
  JsonDetails,
  Metric,
  Pager,
  StatusBadge,
} from "@/components/operational";
import {
  bytes,
  localTime,
  retryEligible,
  short,
  type AgentInfo,
  type EventPage,
  type JobDetail,
  type JobInfo,
  type NodeDetail,
  type Section,
  type Snapshot,
} from "@/lib/contracts";

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/control/${path}`, {
    method: body === undefined ? "GET" : "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(String(response.status));
  return response.json() as Promise<T>;
}
function usePoll<T>(path: string | null, revision: number) {
  const [record, setRecord] = useState<{ path: string; data: T } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (!path) return;
      try {
        if (document.visibilityState === "hidden") return;
        const data = await api<T>(path);
        if (active) {
          setRecord({ path, data });
          setError("");
        }
      } catch (e) {
        if (active) {
          const code = e instanceof Error ? e.message : "unavailable";
          setError(code);
          if (code === "401" || code === "403") setRecord(null);
        }
      } finally {
        if (active) timer = setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [path, revision]);
  return { data: record?.path === path ? record.data : null, error };
}
const labels: Record<Section, string> = {
  overview: "Overview",
  jobs: "Jobs",
  nodes: "Nodes",
  agents: "Agents",
  models: "Models",
  activity: "Activity / Audit",
};

export default function CommandCenter({
  section = "overview",
  detailId,
  authError,
}: {
  section?: Section;
  detailId?: string;
  authError?: string;
}) {
  const [workspace, setWorkspace] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const query = new URLSearchParams({
    section,
    offset: String(offset),
    search,
    status,
    ...(workspace ? { workspace_id: workspace } : {}),
  });
  const state = usePoll<Snapshot>(`command-center?${query}`, revision);
  const identity = usePoll<{
    display_name: string;
    email: string;
    roles: string[];
  }>("auth/me", revision);
  const data = state.data;
  const refresh = () => setRevision((r) => r + 1);
  return (
    <div className="command-layout">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="command-sidebar">
        <a className="brand" href="/">
          THE GODFATHER<span>Command Center</span>
        </a>
        <p className="local-label">Trusted local development</p>
        <nav aria-label="Main navigation">
          {(Object.keys(labels) as Section[]).map((key) => (
            <a
              key={key}
              aria-current={section === key ? "page" : undefined}
              href={key === "overview" ? "/" : `/${key}`}
            >
              {labels[key]}
            </a>
          ))}
          <a href="/administration">Account / Administration</a>
        </nav>
        <p className="sidebar-note">
          PostgreSQL is authoritative.
          <br />
          Phase 07–08 · Local only
        </p>
      </aside>
      <div className="command-body">
        <header className="topbar">
          <span>Infrastructure / {labels[section]}</span>
          <div className="actions">
            <label>
              Theme
              <select
                aria-label="Theme"
                defaultValue="system"
                onChange={(e) => {
                  document.documentElement.dataset.theme = e.target.value;
                }}
              >
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            {identity.data && (
              <span>
                {identity.data.display_name} ? {identity.data.roles.join(", ")}
              </span>
            )}
            {data && (
              <Button
                variant="outline"
                onClick={async () => {
                  const result = await fetch("/api/auth/logout", {
                    method: "POST",
                  });
                  if (!result.ok) {
                    window.alert(
                      "Logout not confirmed; retry when the API is available.",
                    );
                    return;
                  }
                  window.location.assign("/");
                }}
              >
                Sign out
              </Button>
            )}
          </div>
        </header>
        <main id="main-content">
          <div className="page-heading">
            <div>
              <p className="eyebrow">THE GODFATHER / CONTROL PLANE</p>
              <h1>{labels[section]}</h1>
              <p>Real backend state, durable work and recovery activity.</p>
            </div>
            {data && (
              <Button variant="outline" onClick={refresh}>
                Refresh now
              </Button>
            )}
          </div>
          {!data && state.error === "401" ? (
            <GoogleLogin error={authError} />
          ) : (
            <>
              {state.error && (
                <p role="alert" className="notice error">
                  {state.error === "401"
                    ? "Session expired or revoked. Sign in again."
                    : state.error === "403"
                      ? "Permission denied."
                      : "Refresh failed. Displayed data may be stale; no action confirmed."}
                </p>
              )}
              {!data && !state.error && (
                <p role="status" className="panel">
                  Loading authorized backend state…
                </p>
              )}
              {data && (
                <>
                  <section className="scope-bar">
                    <label>
                      Workspace
                      <select
                        value={workspace || data.workspace_id || ""}
                        onChange={(e) => {
                          setWorkspace(e.target.value);
                          setOffset(0);
                        }}
                      >
                        {data.workspaces.map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.name}
                          </option>
                        ))}
                        {!data.workspaces.length && (
                          <option value="">No authorized workspace</option>
                        )}
                      </select>
                    </label>
                    <p role="status">
                      {state.error ? "Stale data" : "Polling every 3 seconds"} ·
                      Updated {localTime(data.generated_at)}
                      <small>
                        Jobs and agents: selected workspace. Nodes: platform
                        health. Workload counts: authorized workspaces only.
                      </small>
                    </p>
                  </section>
                  {detailId ? (
                    <Inspection
                      kind={section}
                      id={detailId}
                      revision={revision}
                      refresh={refresh}
                    />
                  ) : (
                    <>
                      {["nodes", "jobs", "agents"].includes(section) && (
                        <div className="filters">
                          <label>
                            Search {section}
                            <input
                              type="search"
                              placeholder="Name, owner, platform or ID"
                              value={search}
                              onChange={(e) => {
                                setSearch(e.target.value);
                                setOffset(0);
                              }}
                            />
                          </label>
                          {section !== "agents" && (
                            <label>
                              Status
                              <select
                                value={status}
                                onChange={(e) => {
                                  setStatus(e.target.value);
                                  setOffset(0);
                                }}
                              >
                                <option value="">All statuses</option>
                                {(section === "nodes"
                                  ? [
                                      "online",
                                      "suspect",
                                      "offline",
                                      "draining",
                                      "disabled",
                                    ]
                                  : [
                                      "PENDING",
                                      "ASSIGNED",
                                      "RUNNING",
                                      "RETRY_WAIT",
                                      "COMPLETED",
                                      "FAILED",
                                      "CANCELLED",
                                    ]
                                ).map((s) => (
                                  <option key={s}>{s}</option>
                                ))}
                              </select>
                            </label>
                          )}
                        </div>
                      )}
                      {section === "overview" && <Overview data={data} />}
                      {section === "jobs" && (
                        <>
                          <SubmitJob data={data} />
                          <JobTable rows={data.jobs} />
                        </>
                      )}
                      {section === "nodes" && <NodeTable data={data} />}
                      {section === "agents" && (
                        <Agents data={data} refresh={refresh} />
                      )}
                      {section === "models" && (
                        <Models
                          data={data}
                          offset={offset}
                          setOffset={setOffset}
                        />
                      )}
                      {section === "activity" && (
                        <Activity
                          workspace={data.workspace_id}
                          revision={revision}
                        />
                      )}
                      {(section === "jobs" ||
                        section === "nodes" ||
                        section === "agents") && (
                        <Pager
                          offset={offset}
                          limit={data.limit}
                          total={data.totals[section]}
                          onChange={setOffset}
                        />
                      )}
                    </>
                  )}
                </>
              )}
            </>
          )}
        </main>
        <footer>
          Private local control plane · Unsaved files and GPU state are not
          recoverable · BYOK is planning only.
        </footer>
      </div>
    </div>
  );
}

function JobTable({ rows }: { rows: JobInfo[] }) {
  return (
    <DataTable
      caption="Jobs in this scope"
      rows={rows}
      rowKey={(j) => j.id}
      columns={[
        {
          label: "Job / requester",
          cell: (j) => (
            <>
              <a href={`/jobs/${j.id}`}>{short(j.id)}</a>
              <small title={j.owner_id}>Requester {short(j.owner_id)}</small>
            </>
          ),
        },
        {
          label: "Workload",
          cell: (j) => (
            <>
              {j.type}
              <small>Priority {j.priority}</small>
            </>
          ),
        },
        {
          label: "Status",
          cell: (j) => (
            <>
              <StatusBadge value={j.status} />
              {j.cancel_requested_at && <small>Cancellation requested</small>}
              {j.status === "PENDING" && (
                <small>Waiting for a compatible authorized node</small>
              )}
            </>
          ),
        },
        {
          label: "Execution",
          cell: (j) => (
            <>
              {j.assigned_node_id ? (
                <a href={`/nodes/${j.assigned_node_id}`}>
                  {short(j.assigned_node_id)}
                </a>
              ) : (
                "Unassigned"
              )}
              <small>
                Attempt {j.attempt_count} · Fence {j.fencing_token}
              </small>
            </>
          ),
        },
        {
          label: "Durable state",
          cell: (j) =>
            j.checkpoint_ref ? "Checkpoint available" : "No checkpoint",
        },
        { label: "Submitted", cell: (j) => localTime(j.created_at) },
      ]}
    />
  );
}

function NodeTable({ data }: { data: Snapshot }) {
  return (
    <DataTable
      caption="Registered worker nodes"
      rows={data.nodes}
      rowKey={(n) => n.node_id}
      columns={[
        {
          label: "Node / owner",
          cell: (n) => (
            <>
              <a href={`/nodes/${n.node_id}`}>{n.name}</a>
              <small title={n.owner_id}>Owner {short(n.owner_id)}</small>
            </>
          ),
        },
        {
          label: "Health",
          cell: (n) => (
            <>
              <StatusBadge value={n.state} />
              <small>
                {n.resources.source === "simulated"
                  ? "SIMULATED"
                  : "Physical report"}
              </small>
            </>
          ),
        },
        {
          label: "Platform / resources",
          cell: (n) => (
            <>
              {n.os} / {n.architecture}
              <small>
                {n.resources.cpu_count} CPUs · {bytes(n.resources.ram_bytes)}
              </small>
            </>
          ),
        },
        {
          label: "Specialties",
          cell: (n) => (
            <>
              {n.primary_capabilities.join(", ")}
              <small>
                Secondary: {n.secondary_capabilities.join(", ") || "None"}
              </small>
            </>
          ),
        },
        {
          label: "Scheduling",
          cell: (n) => (
            <>
              {n.scheduling_policy}
              <small>
                {n.visible_active_jobs} visible jobs · {n.concurrency_limit}{" "}
                slots
              </small>
            </>
          ),
        },
        { label: "Heartbeat", cell: (n) => localTime(n.last_heartbeat_at) },
      ]}
    />
  );
}

function Overview({ data }: { data: Snapshot }) {
  const total = Object.values(data.node_counts).reduce((a, b) => a + b, 0);
  const readings = data.nodes
    .filter(
      (n) =>
        n.resources.source === "physical" && n.connection_status === "online",
    )
    .map((n) => n.resources.cpu_percent)
    .filter((v): v is number => v !== null);
  return (
    <>
      <div className="metric-grid">
        <Metric
          label="Online / registered nodes"
          value={`${data.node_counts.online || 0} / ${total}`}
          detail="Actual worker reports"
        />
        <Metric
          label="Running / assigned jobs"
          value={`${data.job_counts.RUNNING || 0} / ${data.job_counts.ASSIGNED || 0}`}
        />
        <Metric
          label="Pending / retry wait"
          value={`${data.job_counts.PENDING || 0} / ${data.job_counts.RETRY_WAIT || 0}`}
        />
        <Metric
          label="Enabled agent versions"
          value={data.agent_counts.enabled_versions}
          detail={`${data.agent_counts.active_versions} active · ${data.agent_counts.compatible_online_versions} compatible online · ${data.agent_counts.disabled_versions} disabled`}
        />
      </div>
      <section className="panel">
        <h2>Cluster state</h2>
        <div className="state-strip">
          {["online", "suspect", "offline", "draining", "disabled"].map((s) => (
            <span key={s}>
              <StatusBadge value={s} /> {data.node_counts[s] || 0}
            </span>
          ))}
        </div>
        <div className="state-strip">
          {["COMPLETED", "FAILED", "CANCELLED"].map((s) => (
            <span key={s}>
              <StatusBadge value={s} /> {data.job_counts[s] || 0}
            </span>
          ))}
        </div>
        <p>
          Physical CPU utilization:{" "}
          {readings.length
            ? `${(readings.reduce((a, b) => a + b, 0) / readings.length).toFixed(1)}% mean of ${readings.length} reported nodes on this page`
            : "Unavailable — no online physical readings"}
          .
        </p>
        <p>
          {data.models.filter((m) => m.available).length} available deployments
          on the first page in this workspace.{" "}
          <a href="/models">Inspect models</a>.
        </p>
        <p className="muted">
          Simulated readings are excluded from physical utilization. Unknown
          telemetry is distinct from zero.
        </p>
      </section>
      <section className="panel">
        <h2>Recent jobs</h2>
        <JobTable rows={data.jobs.slice(0, 8)} />
      </section>
      <div className="two-columns">
        <section className="panel">
          <h2>Recent failover and recovery</h2>
          <EventTimeline
            events={data.events.items
              .filter((e) =>
                /recovery|interrupted|resumed|review_required/.test(e.type),
              )
              .slice(0, 8)}
          />
        </section>
        <section className="panel">
          <h2>Recent events and errors</h2>
          <EventTimeline events={data.events.items.slice(0, 8)} />
        </section>
      </div>
    </>
  );
}

function SubmitJob({ data }: { data: Snapshot }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      const a = data.agents.find((a) => a.version_id === f.get("agent"));
      const job = await api<JobInfo>("workflow/jobs", {
        workspace_id: data.workspace_id,
        agent_id: a?.id,
        agent_version: a?.version,
        input: { instruction: f.get("instruction") },
        priority: Number(f.get("priority")),
      });
      window.location.assign(`/jobs/${job.id}`);
    } catch {
      setError(
        "Submission not confirmed. Check permissions, agent availability and backend connection.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="panel submission">
      <summary>Submit a job</summary>
      <form onSubmit={submit}>
        <p>Recoverable read-only workflow</p>
        <label>
          Agent and pinned version
          <select name="agent" required>
            {data.agents
              .filter((a) => a.enabled)
              .map((a) => (
                <option key={a.version_id} value={a.version_id}>
                  {a.definition.name} ? v{a.version}
                </option>
              ))}
          </select>
        </label>
        <label>
          Instruction
          <textarea name="instruction" required maxLength={4096} rows={3} />
        </label>
        <details>
          <summary>Advanced options</summary>
          <label>
            Priority
            <input
              name="priority"
              type="number"
              defaultValue={0}
              min={-100}
              max={100}
            />
          </label>
          <p className="muted">
            Workflow resources, models, allowed tools, retries and timeout come
            from the pinned definition. No shell or repository access is
            granted.
          </p>
        </details>
        {error && <p role="alert">{error}</p>}
        <Button
          disabled={
            busy || !data.workspace_id || !data.agents.some((a) => a.enabled)
          }
        >
          {busy ? "Submitting…" : "Submit job"}
        </Button>
        <p className="muted">
          Submission queues work. Execution requires a compatible authorized
          worker.
        </p>
      </form>
    </details>
  );
}

function Inspection({
  kind,
  id,
  revision,
  refresh,
}: {
  kind: Section;
  id: string;
  revision: number;
  refresh: () => void;
}) {
  const state = usePoll<JobDetail | NodeDetail>(
    `command-center/${kind}/${id}`,
    revision,
  );
  if (!state.data)
    return (
      <p role="status">
        {state.error
          ? "Record unavailable or permission denied."
          : "Loading inspection…"}
      </p>
    );
  return (
    <section className="panel inspection">
      <a href={`/${kind}`}>Back to {kind}</a>
      {state.error && (
        <p role="alert">Refresh failed; displayed details are stale.</p>
      )}
      {"job" in state.data ? (
        <JobInspection detail={state.data} refresh={refresh} />
      ) : (
        <NodeInspection detail={state.data} refresh={refresh} />
      )}
    </section>
  );
}

function JobInspection({
  detail,
  refresh,
}: {
  detail: JobDetail;
  refresh: () => void;
}) {
  const j = detail.job;
  const [artifact, setArtifact] = useState<unknown>(undefined);
  const [error, setError] = useState("");
  return (
    <>
      <h2>Job {short(j.id)}</h2>
      <div className="state-strip">
        <StatusBadge value={j.status} />
        {detail.workflow && <StatusBadge value={detail.workflow.status} />}
        <span>
          Attempt {j.attempt_count} · Fence {j.fencing_token}
        </span>
      </div>
      <dl>
        <dt>Job ID</dt>
        <dd>{j.id}</dd>
        <dt>Requester / workspace</dt>
        <dd>
          {j.owner_id} / {j.workspace_id}
        </dd>
        <dt>Assigned worker</dt>
        <dd>
          {j.assigned_node_id ? (
            <a href={`/nodes/${j.assigned_node_id}`}>{j.assigned_node_id}</a>
          ) : (
            "Unassigned"
          )}
        </dd>
        <dt>Workload / priority</dt>
        <dd>
          {j.type} / {j.priority}
        </dd>
        <dt>Progress</dt>
        <dd>
          {detail.workflow
            ? `${detail.workflow.current_step} committed steps; checkpoint v${detail.workflow.checkpoint_version}`
            : "See execution history"}
        </dd>
        <dt>Recovery</dt>
        <dd>
          {detail.workflow?.status === "REVIEW_REQUIRED"
            ? `Requires manual review: ${detail.workflow.recovery_error}`
            : j.status === "PENDING"
              ? "Waiting for a compatible authorized node"
              : j.status === "RETRY_WAIT"
                ? `Retry at ${localTime(j.next_run_at)}`
                : "See linked attempts below"}
        </dd>
      </dl>
      <div className="actions">
        {detail.can_control &&
          !["FAILED", "CANCELLED", "COMPLETED"].includes(j.status) &&
          !j.cancel_requested_at && (
            <ConfirmAction
              label="Cancel job"
              description="Request durable cancellation. Committed checkpoints remain; completion is blocked and uncommitted local work may be lost."
              onConfirm={async () => {
                await api(`jobs/${j.id}/cancel`, {});
                refresh();
              }}
            />
          )}
        {detail.can_control && retryEligible(detail) && (
          <ConfirmAction
            label="Retry job"
            description="Queue a bounded retry. Committed steps remain; uncommitted read-only work may repeat. Permissions are rechecked."
            onConfirm={async () => {
              await api(`jobs/${j.id}/retry`, {});
              refresh();
            }}
          />
        )}
      </div>
      <JsonDetails
        label="Execution requirements and retry policy"
        value={{ requirements: j.requirements, retry: j.retry }}
      />
      <h3>Execution attempts</h3>
      <DataTable
        caption="Original and recovery attempts"
        rows={detail.attempts}
        rowKey={(a) => a.id}
        columns={[
          {
            label: "Attempt",
            cell: (a) => (
              <>
                {a.number} · {short(a.id)}
                <small>Fence {a.fencing_token}</small>
              </>
            ),
          },
          {
            label: "Worker",
            cell: (a) => <a href={`/nodes/${a.node_id}`}>{short(a.node_id)}</a>,
          },
          {
            label: "Status",
            cell: (a) => (
              <>
                <StatusBadge value={a.status} />
                <small>{String(a.error.code || "")}</small>
              </>
            ),
          },
          {
            label: "Recovery origin",
            cell: (a) =>
              a.recovered_from_attempt_id ? (
                <>
                  <span>From {short(a.recovered_from_attempt_id)}</span>
                  <small>
                    {a.resumed_checkpoint_version
                      ? `Resumed checkpoint v${a.resumed_checkpoint_version}`
                      : "Restarted from beginning"}
                  </small>
                </>
              ) : (
                "Original execution"
              ),
          },
          {
            label: "Timing",
            cell: (a) => (
              <>
                {localTime(a.created_at)}
                <small>Finished: {localTime(a.finished_at)}</small>
              </>
            ),
          },
        ]}
      />
      {!!detail.steps.length && (
        <>
          <h3>Workflow steps</h3>
          <DataTable
            caption="Durable workflow progress"
            rows={detail.steps}
            rowKey={(s) => s.id}
            columns={[
              { label: "Step", cell: (s) => s.step_id },
              {
                label: "Status",
                cell: (s) => <StatusBadge value={s.status} />,
              },
              { label: "Attempt", cell: (s) => short(s.attempt_id) },
              {
                label: "Artifact",
                cell: (s) => s.output_artifact_id || "Uncommitted",
              },
              {
                label: "Usage",
                cell: (s) => (
                  <JsonDetails label="Inspect metadata" value={s.metadata} />
                ),
              },
            ]}
          />
        </>
      )}
      {!!detail.checkpoints.length && (
        <>
          <h3>Durable checkpoints</h3>
          <DataTable
            caption="Integrity-checked checkpoint references"
            rows={detail.checkpoints}
            rowKey={(c) => c.id}
            columns={[
              { label: "Version", cell: (c) => `v${c.version}` },
              { label: "Original attempt", cell: (c) => short(c.attempt_id) },
              {
                label: "Artifact",
                cell: (c) => (
                  <>
                    <code>{c.artifact.id}</code>
                    <small title={c.artifact.checksum}>
                      SHA-256 {short(c.artifact.checksum)} ·{" "}
                      {c.artifact.size_bytes} bytes
                    </small>
                  </>
                ),
              },
              {
                label: "Inspect",
                cell: (c) => (
                  <button
                    className="action secondary"
                    onClick={async () => {
                      try {
                        setError("");
                        setArtifact(
                          await api(
                            `workflow/jobs/${j.id}/artifacts/${c.artifact.id}`,
                          ),
                        );
                      } catch {
                        setError(
                          "Artifact unavailable, corrupt or permission denied.",
                        );
                      }
                    }}
                  >
                    View checkpoint v{c.version}
                  </button>
                ),
              },
            ]}
          />
        </>
      )}
      {error && <p role="alert">{error}</p>}
      {artifact !== undefined && (
        <JsonDetails label="Checkpoint artifact content" value={artifact} />
      )}
      <h3>Result and errors</h3>
      <JsonDetails
        label="Authoritative result"
        value={
          detail.output || j.result || detail.attempts.at(-1)?.error || null
        }
      />
      <h3>Failover and lifecycle history</h3>
      <p className="muted">
        Latest {detail.events.items.length} of {detail.events.total} events,
        newest first. Activity provides paged filters.
      </p>
      <EventTimeline events={detail.events.items} />
    </>
  );
}

function NodeInspection({
  detail,
  refresh,
}: {
  detail: NodeDetail;
  refresh: () => void;
}) {
  const n = detail.node;
  return (
    <>
      <h2>{n.name}</h2>
      <div className="state-strip">
        <StatusBadge value={n.state} />
        <span>
          {n.resources.source === "simulated"
            ? "SIMULATED NODE AND HARDWARE"
            : "Physical worker report"}
        </span>
      </div>
      <dl>
        <dt>Identity / owner</dt>
        <dd>
          {n.node_id} / {n.owner_id}
        </dd>
        <dt>Platform</dt>
        <dd>
          {n.os_version} / {n.architecture} · Protocol {n.protocol_version}
        </dd>
        <dt>Connection / heartbeat</dt>
        <dd>
          {n.connection_status} / {localTime(n.last_heartbeat_at)}
        </dd>
        <dt>CPU</dt>
        <dd>
          {n.resources.cpu_name} · {n.resources.cpu_count} CPUs ·{" "}
          {n.resources.cpu_percent == null
            ? "Unavailable"
            : `${n.resources.cpu_percent}%`}{" "}
          utilization
        </dd>
        <dt>RAM</dt>
        <dd>
          {bytes(n.resources.ram_bytes)} total ·{" "}
          {bytes(n.resources.available_ram_bytes)} available
        </dd>
        <dt>GPU / VRAM</dt>
        <dd>
          {n.resources.gpus.length
            ? n.resources.gpus.map((g) => (
                <p key={g.name}>
                  {g.name} · {g.backend} ·{" "}
                  {g.unified_memory ? "Unified memory" : bytes(g.memory_bytes)}{" "}
                  ·{" "}
                  {g.utilization_percent == null
                    ? "Unavailable"
                    : `${g.utilization_percent}%`}{" "}
                  utilization
                </p>
              ))
            : "No reported GPU"}
        </dd>
        <dt>Specialties</dt>
        <dd>
          Primary: {n.primary_capabilities.join(", ")} · Secondary:{" "}
          {n.secondary_capabilities.join(", ") || "None"}
        </dd>
        <dt>Scheduling</dt>
        <dd>
          {n.scheduling_policy} · {n.concurrency_limit} concurrent slots
        </dd>
      </dl>
      <div className="actions">
        {detail.can_control &&
          ["drain", "disable", "enable", "revoke"].map((action) => (
            <ConfirmAction
              key={action}
              label={`${action[0].toUpperCase() + action.slice(1)} node`}
              description={`${action === "drain" ? "Stop new assignments; active work can finish." : action === "disable" ? "Block worker requests and new work. Active attempts expire and may recover elsewhere." : action === "revoke" ? "Permanently invalidate this machine credential. Reconnection and reports are denied; active attempts expire and may recover elsewhere." : "Restore scheduling eligibility when health permits."} Owner tool, host and workspace restrictions remain enforced.`}
              onConfirm={async () => {
                await api(`nodes/${n.node_id}/control`, { action });
                refresh();
              }}
            />
          ))}
      </div>
      <JsonDetails label="Available models" value={n.model_deployments} />
      <JsonDetails
        label="Owner-granted tools and execution environments"
        value={{
          tools: n.worker_tools,
          permissions: n.tool_permissions,
          runtimes: n.runtimes,
          dependencies: n.dependencies,
          toolchains: n.toolchains,
          sandbox_modes: n.sandbox_modes,
        }}
      />
      <h3>Assigned and historical jobs</h3>
      <p className="muted">
        Latest 100 jobs in your authorized workspaces. Other private jobs are
        excluded.
      </p>
      <JobTable rows={detail.jobs} />
      <h3>Activity and errors</h3>
      <EventTimeline events={detail.events.items} />
    </>
  );
}

function Agents({ data, refresh }: { data: Snapshot; refresh: () => void }) {
  const [selected, setSelected] = useState<AgentInfo | null>(null);
  const history = usePoll<{ events: EventPage; assignments: unknown[] }>(
    selected ? `command-center/agents/${selected.id}` : null,
    0,
  );
  return (
    <>
      <DataTable
        caption="Registered immutable agent versions"
        rows={data.agents}
        rowKey={(a) => a.version_id}
        columns={[
          {
            label: "Agent",
            cell: (a) => (
              <button className="text-button" onClick={() => setSelected(a)}>
                {a.definition.name}
              </button>
            ),
          },
          {
            label: "Version / state",
            cell: (a) => (
              <>
                v{a.version}{" "}
                <StatusBadge value={a.enabled ? "enabled" : "disabled"} />
              </>
            ),
          },
          {
            label: "Model / capabilities",
            cell: (a) => (
              <JsonDetails
                label="Requirements"
                value={a.definition.requirements}
              />
            ),
          },
          {
            label: "Tools",
            cell: (a) =>
              a.definition.allowed_tools
                .map((t) => `${t.name}@${t.version}`)
                .join(", ") || "None",
          },
          {
            label: "Workflow",
            cell: (a) =>
              `${a.definition.workflow.steps.length} steps · v${a.definition.workflow.version}`,
          },
          {
            label: "Control",
            cell: (a) =>
              data.workspaces.find((w) => w.id === data.workspace_id)
                ?.can_manage ? (
                <ConfirmAction
                  label={a.enabled ? "Disable agent" : "Enable agent"}
                  description="Change availability for this version. Disabling prevents new step starts. Cancel a job to stop current execution."
                  onConfirm={async () => {
                    await api(`agents/${a.id}/versions/${a.version}/control`, {
                      action: a.enabled ? "disable" : "enable",
                    });
                    setSelected(null);
                    refresh();
                  }}
                />
              ) : (
                "Workspace administration required"
              ),
          },
        ]}
      />
      {selected && (
        <section className="panel">
          <h2>
            {selected.definition.name} · v{selected.version}
          </h2>
          <p>{selected.definition.description}</p>
          <p>
            Owner {selected.owner_id} · Agent {selected.id}
          </p>
          <JsonDetails
            label="Immutable definition and tool permissions"
            value={selected.definition}
          />
          <h3>Workflow execution history</h3>
          {history.error && <p role="alert">History unavailable.</p>}
          {!history.data && !history.error && (
            <p role="status">Loading workflow history…</p>
          )}
          {history.data && (
            <>
              <JsonDetails
                label="Assigned model deployments and observed usage (latest 100 model steps)"
                value={history.data.assignments}
              />
              <EventTimeline events={history.data.events.items} />
            </>
          )}
          <button
            className="action secondary"
            onClick={() => setSelected(null)}
          >
            Close inspection
          </button>
        </section>
      )}
    </>
  );
}

function Models({
  data,
  offset,
  setOffset,
}: {
  data: Snapshot;
  offset: number;
  setOffset: (n: number) => void;
}) {
  return (
    <>
      <p className="muted">
        Permitted deployments for this workspace. Provider aliases contain no
        credentials. BYOK remains unimplemented.
      </p>
      <DataTable
        caption="Model deployments"
        rows={data.models}
        rowKey={(m) =>
          `${m.node_id}:${m.deployment.provider_id}:${m.deployment.identifier}`
        }
        columns={[
          {
            label: "Model / provider",
            cell: (m) => (
              <>
                {m.deployment.identifier}
                <small>
                  {m.deployment.provider} / {m.deployment.provider_id}
                </small>
              </>
            ),
          },
          {
            label: "Host",
            cell: (m) => <a href={`/nodes/${m.node_id}`}>{short(m.node_id)}</a>,
          },
          {
            label: "Availability",
            cell: (m) => (
              <StatusBadge value={m.available ? "available" : "unavailable"} />
            ),
          },
          {
            label: "Capabilities",
            cell: (m) => (
              <>
                {m.deployment.verified_capabilities.join(", ") ||
                  "None verified"}
                <small>
                  Declared:{" "}
                  {m.deployment.declared_capabilities.join(", ") || "None"}
                </small>
              </>
            ),
          },
          {
            label: "Context / memory",
            cell: (m) => (
              <>
                {m.deployment.context_window ?? "Unknown"} context tokens
                <small>
                  RAM {bytes(m.deployment.estimated_ram_bytes)} · VRAM{" "}
                  {bytes(m.deployment.estimated_vram_bytes)}
                </small>
              </>
            ),
          },
          {
            label: "Observed inference",
            cell: (m) => {
              const usage = data.metrics?.recent_attempts.find(
                (a) => a.node_id === m.node_id && a.usage,
              )?.usage;
              return usage ? (
                <>
                  {usage.duration_seconds?.toFixed(2)}s
                  <small>
                    {usage.output_tokens ?? "Unknown"} output tokens ·{" "}
                    {usage.tokens_per_second?.toFixed(1) ?? "Unknown"} tokens/s
                  </small>
                </>
              ) : (
                "No recent measurement"
              );
            },
          },
        ]}
      />
      <div className="pager">
        <button
          className="action secondary"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - data.limit))}
        >
          Previous deployments
        </button>
        <span>
          From {offset + 1}; up to {data.limit} per page
        </span>
        <button
          className="action secondary"
          disabled={data.models.length < data.limit}
          onClick={() => setOffset(offset + data.limit)}
        >
          Next deployments
        </button>
      </div>
      <p className="muted">
        Performance is per node, sampled from up to 200 recent inference
        attempts; it is not a model benchmark.
      </p>
    </>
  );
}

function Activity({
  workspace,
  revision,
}: {
  workspace: string | null;
  revision: number;
}) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const query = new URLSearchParams({
    ...filters,
    offset: String(offset),
    ...(workspace ? { workspace_id: workspace } : {}),
  });
  const state = usePoll<EventPage>(`command-center/events?${query}`, revision);
  return (
    <section className="panel">
      <h2>Events and audit history</h2>
      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          const next: Record<string, string> = {};
          for (const [key, value] of new FormData(e.currentTarget).entries())
            if (typeof value === "string" && value)
              next[key] = ["since", "until"].includes(key)
                ? new Date(value).toISOString()
                : value;
          setFilters(next);
          setOffset(0);
        }}
      >
        {["node_id", "user_id", "job_id", "agent_id", "event_type"].map(
          (key) => (
            <label key={key}>
              {key.replaceAll("_", " ")}
              <input
                name={key}
                placeholder={key === "event_type" ? "Exact event type" : "UUID"}
              />
            </label>
          ),
        )}
        <label>
          Severity
          <select name="severity">
            <option value="">All</option>
            <option>info</option>
            <option>warning</option>
            <option>error</option>
          </select>
        </label>
        <label>
          From (local time)
          <input type="datetime-local" name="since" />
        </label>
        <label>
          Until (local time)
          <input type="datetime-local" name="until" />
        </label>
        <Button>Apply filters</Button>
        <button
          className="action secondary"
          type="reset"
          onClick={() => {
            setFilters({});
            setOffset(0);
          }}
        >
          Clear filters
        </button>
      </form>
      {state.error && (
        <p role="alert">
          Events unavailable. Check filter IDs, time range and permissions.
        </p>
      )}
      {!state.data && !state.error && <p role="status">Loading events…</p>}
      <EventTimeline events={state.data?.items || []} />
      {state.data && (
        <Pager
          offset={offset}
          total={state.data.total}
          limit={state.data.limit}
          onChange={setOffset}
        />
      )}
      <p className="muted">
        Severity is derived from event type and health transitions. Workspace
        events remain private.
      </p>
    </section>
  );
}
