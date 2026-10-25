"use client";
import { Avatar } from "./avatar";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { short, type JobInfo, type NodeInfo } from "../lib/contracts";

export function JobExecution({ job }: { job: JobInfo }) {
  const execution = job.execution;
  if (!execution)
    return job.assigned_node_id ? (
      <a href={`/nodes/${job.assigned_node_id}`}>
        {short(job.assigned_node_id)}
      </a>
    ) : (
      <>
        {job.attempt_count
          ? "Execution history unavailable"
          : "Not yet assigned"}
      </>
    );
  const name = execution.node_name || short(execution.node_id);
  return (
    <>
      {execution.can_inspect_node ? (
        <a href={`/nodes/${execution.node_id}`} title={execution.node_id}>
          {name}
        </a>
      ) : (
        <span title={execution.node_id}>{name}</span>
      )}
      <small>
        Owner{" "}
        {execution.owner_id ? (
          <UserName id={execution.owner_id} name={execution.owner_name} />
        ) : (
          "Unavailable"
        )}
      </small>
      {!job.assigned_node_id && (
        <small>Last attempt {execution.attempt_number}</small>
      )}
    </>
  );
}

const Builds = createContext<Record<string, string>>({});
const versionPattern =
  /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/;

// Semantic precedence, including rc.10 after rc.9; build metadata is not precedence.
export function compareVersions(a: string, b: string): number | null {
  const left = versionPattern.exec(a),
    right = versionPattern.exec(b);
  if (!left || !right) return null;
  for (let i = 1; i <= 3; i++) {
    const difference = Number(left[i]) - Number(right[i]);
    if (difference) return difference;
  }
  if (!left[4] || !right[4]) return left[4] ? -1 : right[4] ? 1 : 0;
  const l = left[4].split("."),
    r = right[4].split(".");
  for (let i = 0; i < Math.max(l.length, r.length); i++) {
    if (l[i] === undefined) return -1;
    if (r[i] === undefined) return 1;
    if (l[i] === r[i]) continue;
    const ln = /^\d+$/.test(l[i]),
      rn = /^\d+$/.test(r[i]);
    if (ln && rn) return Number(l[i]) - Number(r[i]);
    if (ln !== rn) return ln ? -1 : 1;
    return l[i] < r[i] ? -1 : 1;
  }
  return 0;
}

export function availableBuilds(data: unknown): Record<string, string> {
  const result: Record<string, string> = {};
  if (
    !data ||
    typeof data !== "object" ||
    !("artifacts" in data) ||
    !Array.isArray(data.artifacts)
  )
    return result;
  for (const item of data.artifacts) {
    if (
      !item ||
      typeof item.filename !== "string" ||
      typeof item.sha256 !== "string" ||
      !/^[a-f0-9]{64}$/.test(item.sha256)
    )
      continue;
    const match =
      /^(?:godfather-worker|consigliere)-(.+)-(windows-x64-setup\.exe|macos-(arm64|x64)-installer\.dmg|linux-(arm64|x64)\.zip)$/.exec(
        item.filename,
      );
    if (!match || !versionPattern.test(match[1])) continue;
    const target = match[2].startsWith("windows")
      ? "windows-x86_64"
      : match[4]
        ? `linux-${match[4] === "x64" ? "x86_64" : "arm64"}`
        : match[3] === "arm64"
          ? "macos-arm64"
          : "macos-x86_64";
    if (!result[target] || (compareVersions(match[1], result[target]) ?? 0) > 0)
      result[target] = match[1];
  }
  return result;
}

export function WorkerBuildProvider({ children }: { children: ReactNode }) {
  const [builds, setBuilds] = useState<Record<string, string>>({});
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = () => {
      void fetch("/downloads/manifest.json", {
        cache: "no-store",
        signal: controller.signal,
      })
        .then(async (response) => {
          if (response.ok) setBuilds(availableBuilds(await response.json()));
        })
        .catch(() => {})
        .finally(() => {
          if (active) timer = setTimeout(refresh, 60000);
        });
    };
    refresh();
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, []);
  return <Builds.Provider value={builds}>{children}</Builds.Provider>;
}

export function UserName({
  id,
  name,
  picture,
  location,
  fallback = "Unknown user",
}: {
  id: string;
  name?: string | null;
  picture?: string | null;
  location?: string | null;
  fallback?: string;
}) {
  return (
    <span
      className="owner-name"
      tabIndex={0}
      title={location ? `${id} · ${location}` : id}
      aria-label={`${name || fallback}, user ID ${id}`}
    >
      <Avatar name={name || fallback} picture={picture} /> {name || fallback}
      <span role="tooltip" className="owner-tooltip">
        {id}
        {location ? ` · ${location}` : ""}
      </span>
    </span>
  );
}
export function OwnerName({
  node,
}: {
  node: Pick<
    NodeInfo,
    "owner_id" | "owner_name" | "owner_picture" | "owner_location"
  >;
}) {
  return (
    <UserName
      id={node.owner_id}
      name={node.owner_name}
      picture={node.owner_picture}
      location={node.owner_location}
      fallback="Unknown owner"
    />
  );
}
export function WorkerVersion({
  node,
}: {
  node: Pick<NodeInfo, "worker_version" | "os" | "architecture">;
}) {
  const latest = useContext(Builds)[`${node.os}-${node.architecture}`];
  const comparison =
    node.worker_version && latest
      ? compareVersions(node.worker_version, latest)
      : null;
  return (
    <span className="worker-version">
      {node.worker_version || "Not reported"}
      {comparison !== null && comparison < 0 && (
        <span
          className="badge worker-outdated"
          title={`Latest build for this platform: ${latest}`}
        >
          Update Available
        </span>
      )}
      <small>
        {latest
          ? `Latest: ${latest}`
          : "Latest build unavailable for this platform"}
      </small>
    </span>
  );
}
