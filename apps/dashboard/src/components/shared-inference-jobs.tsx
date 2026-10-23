"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApplicationShell, RibbonGroup } from "./application-shell";
import { JobResult } from "./job-result";
import { StatusBadge } from "./operational";
import { useFeedback } from "./toast-notifications";
import { control } from "../lib/control-client";
import {
  localTime,
  type JobInfo,
  type JobDetail,
  type Page,
  type Snapshot,
} from "../lib/contracts";

type Mode = "single_host" | "local_network" | "wide_area";
export const inferenceModes: { id: Mode; name: string; description: string }[] =
  [
    {
      id: "single_host",
      name: "GPUs inside one computer",
      description:
        "One model split across multiple local GPUs. Requires a configured multi-device inference engine.",
    },
    {
      id: "local_network",
      name: "Computers on a fast local network",
      description:
        "One model split across consenting computers over a private LAN. Network overhead affects performance.",
    },
    {
      id: "wide_area",
      name: "Computers across locations",
      description:
        "One model across a private connection between locations, including Vegas and LA. Experimental; internet latency can make generation slower.",
    },
  ];
interface InferenceGroup {
  id: string;
  name: string;
  mode: Mode;
  model: string;
  engine: string;
  parallelism: string;
  device_count: number;
  available: boolean;
  reason: string;
  computers: { id: string; name: string }[];
}
export function InferenceSetups({
  mode,
  select,
}: {
  mode: Mode;
  select: (mode: Mode) => void;
}) {
  return (
    <fieldset className="inference-setups">
      <legend>Execution setup</legend>
      {inferenceModes.map((setup) => (
        <label
          key={setup.id}
          className={`inference-setup ${mode === setup.id ? "selected" : ""}`}
        >
          <input
            className="form-check-input"
            type="radio"
            name="inference-mode"
            value={setup.id}
            checked={mode === setup.id}
            onChange={() => select(setup.id)}
          />
          <strong>{setup.name}</strong>
          <span>{setup.description}</span>
        </label>
      ))}
    </fieldset>
  );
}
export default function SharedInferenceJobs({
  user,
  initialWorkspace = "",
}: {
  user: { id: string; display_name: string; roles: string[] };
  initialWorkspace?: string;
}) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [workspace, setWorkspace] = useState(initialWorkspace);
  const [mode, setMode] = useState<Mode>("single_host");
  const [groups, setGroups] = useState<InferenceGroup[]>([]);
  const [groupId, setGroupId] = useState("");
  const [history, setHistory] = useState<Page<JobInfo> | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [error, setError] = useState("");
  useFeedback(error);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const workspaceId =
    workspace || data?.workspace_id || data?.workspaces[0]?.id || "";
  useEffect(() => {
    let active = true;
    void control<Snapshot>(
      `command-center?section=jobs${workspace ? `&workspace_id=${workspace}` : ""}`,
    )
      .then((snapshot) => {
        if (active) setData(snapshot);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [workspace, revision]);
  useEffect(() => {
    if (!workspaceId) return;
    let active = true,
      loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const [options, page, current] = await Promise.all([
          control<{ groups: InferenceGroup[] }>(
            `shared-inference/options?workspace_id=${workspaceId}`,
          ),
          control<Page<JobInfo>>(
            `shared-inference/jobs?workspace_id=${workspaceId}&offset=${offset}&limit=25`,
          ),
          selected
            ? control<JobDetail>(`command-center/jobs/${selected}`)
            : Promise.resolve(null),
        ]);
        if (active) {
          setGroups(options.groups);
          setHistory(page);
          setDetail(current);
          setStale(false);
        }
      } catch (e) {
        if (active) {
          setStale(true);
          setError(e instanceof Error ? e.message : "Status unavailable");
        }
      } finally {
        loading = false;
      }
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [workspaceId, offset, selected, revision]);
  const matching = groups.filter((group) => group.mode === mode);
  const group = matching.find((entry) => entry.id === groupId);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!group?.available || stale) {
      setError(
        "Choose a ready inference group. Each computer owner must configure and opt in to the same private engine topology.",
      );
      return;
    }
    const form = new FormData(event.currentTarget);
    if (!String(form.get("prompt") || "").trim()) {
      setError("Enter the job prompt.");
      return;
    }
    if (mode === "wide_area" && form.get("wide_area_consent") !== "on") {
      setError(
        "Confirm sharing this prompt between locations and experimental network performance.",
      );
      return;
    }
    setBusy(true);
    try {
      const job = await control<JobInfo>(
        "shared-inference/jobs",
        {
          workspace_id: workspaceId,
          group_id: group.id,
          prompt: form.get("prompt"),
          wide_area_consent: form.get("wide_area_consent") === "on",
        },
        30000,
      );
      setSelected(job.id);
      setDetail(null);
      setOffset(0);
      setRevision((v) => v + 1);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Submission not confirmed. Check history before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }
  const pages = (
    <div className="actions" aria-label="Distributed inference pagination">
      <button
        className="btn btn-outline-primary action secondary"
        disabled={!offset}
        onClick={() => setOffset(Math.max(0, offset - 25))}
      >
        Previous
      </button>
      <span>
        {history?.total
          ? `${offset + 1}-${Math.min(offset + 25, history.total)} of ${history.total}`
          : "No jobs"}
      </span>
      <button
        className="btn btn-outline-primary action secondary"
        disabled={!history || offset + 25 >= history.total}
        onClick={() => setOffset(offset + 25)}
      >
        Next
      </button>
    </div>
  );
  return (
    <ApplicationShell
      section="distributed"
      account={user}
      data={data}
      stale={stale}
      refresh={() => setRevision((v) => v + 1)}
      ribbon={
        <RibbonGroup label="Related work">
          <a
            className="btn btn-outline-primary action secondary"
            href={`/distributed-tasks?workspace=${workspaceId}`}
          >
            Distributed Tasks
          </a>
          <a className="btn btn-outline-primary action secondary" href="/nodes">
            Worker computers
          </a>
        </RibbonGroup>
      }
    >
      <main id="main-content" className="container-fluid distributed-page">
        <h1>Distributed Jobs</h1>
        <p>
          One job, one coordinated model, one answer. A configured engine shares
          model computation across the selected devices.
        </p>
        {error && <p role="alert">{error}</p>}
        {stale && (
          <p role="status">
            Connection interrupted. Displayed availability may be stale.
          </p>
        )}
        <details className="card panel" open>
          <summary>Submit a shared inference job</summary>
          <form onSubmit={(event) => void submit(event)} noValidate>
            <label>
              Workspace
              <select
                className="form-select"
                value={workspaceId}
                onChange={(event) => {
                  setWorkspace(event.target.value);
                  setSelected("");
                  setGroupId("");
                  setDetail(null);
                  setOffset(0);
                }}
              >
                {data?.workspaces.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <InferenceSetups
              mode={mode}
              select={(value) => {
                setMode(value);
                setGroupId("");
              }}
            />
            <label>
              Inference group
              <select
                className="form-select"
                value={groupId}
                onChange={(event) => setGroupId(event.target.value)}
              >
                <option value="">Choose an owner-configured group</option>
                {matching.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.name} - {entry.model} -{" "}
                    {entry.available ? "Ready" : "Unavailable"}
                  </option>
                ))}
              </select>
            </label>
            {!matching.length && (
              <p role="status">
                No groups configured for this setup. Each participating owner
                must opt in locally, and the leader must discover the shared
                engine model. Installing the same model on several computers
                does not create a group.
              </p>
            )}
            {group && (
              <div className="submission-readiness">
                <strong>{group.model}</strong>
                <p>
                  {group.engine} - {group.parallelism} parallelism -{" "}
                  {group.device_count} configured devices
                </p>
                <p>
                  {group.computers.map((computer) => computer.name).join(", ")}
                </p>
                <p>{group.reason}</p>
              </div>
            )}
            <label>
              Job prompt
              <textarea
                className="form-control"
                name="prompt"
                maxLength={32768}
                required
                rows={5}
              />
            </label>
            {mode === "wide_area" && (
              <label className="check-label">
                <input
                  className="form-check-input"
                  type="checkbox"
                  name="wide_area_consent"
                />
                I confirm sharing this prompt across the selected locations and
                understand that generation may be slower.
              </label>
            )}
            <p className="muted">
              All participating computers are reserved together. A member
              disconnect ends the attempt; GPU state cannot be resumed.
              Performance remains unverified until benchmarked on these devices.
            </p>
            <button className="btn btn-primary action" disabled={busy || stale}>
              {busy ? "Submitting..." : "Run distributed job"}
            </button>
          </form>
        </details>
        <section className="card panel">
          <h2>Distributed job history</h2>
          {pages}
          <div
            className="table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Shared inference jobs"
          >
            <table className="table align-middle">
              <caption>One model request per job</caption>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Status</th>
                  <th>Submitted</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {history?.items.map((job) => (
                  <tr key={job.id}>
                    <td>{job.id.slice(0, 8)}</td>
                    <td>
                      <StatusBadge value={job.status} />
                    </td>
                    <td>{localTime(job.created_at)}</td>
                    <td>
                      <button
                        className="btn btn-outline-primary action secondary"
                        onClick={() => {
                          setSelected(job.id);
                          setDetail(null);
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
                {history?.items.length === 0 && (
                  <tr>
                    <td colSpan={4}>
                      No shared inference jobs in this workspace.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {pages}
        </section>
        {detail && (
          <section className="card panel">
            <h2>Job information</h2>
            <StatusBadge value={detail.job.status} />
            <JobResult detail={detail} />
            <a href={`/jobs/${detail.job.id}`}>
              Open attempts, cancellation and full results
            </a>
          </section>
        )}
      </main>
    </ApplicationShell>
  );
}
