export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };
export interface Resource {
  source: "physical" | "simulated";
  cpu_name: string;
  cpu_count: number;
  ram_bytes: number | null;
  available_ram_bytes: number | null;
  cpu_percent: number | null;
  gpus: {
    name: string;
    backend: string;
    memory_bytes: number | null;
    memory_used_bytes: number | null;
    utilization_percent: number | null;
    unified_memory: boolean;
  }[];
  hardware?: {
    cpu_count: number;
    ram_bytes: number | null;
    available_ram_bytes: number | null;
    gpus: Resource["gpus"];
  } | null;
}
export interface NodeInfo {
  owner_name?: string | null;
  owner_picture?: string | null;
  owner_location?: string | null;
  worker_version?: string | null;
  node_id: string;
  owner_id: string;
  name: string;
  os: string;
  os_version: string;
  architecture: string;
  state: string;
  connection_status: string;
  last_heartbeat_at: string | null;
  protocol_version: number;
  resources: Resource;
  scheduling_policy: string;
  share_with_workspaces?: boolean;
  concurrency_limit: number;
  visible_active_jobs: number;
  primary_capabilities: string[];
  secondary_capabilities: string[];
  runtimes: string[];
  toolchains: string[];
  dependencies: string[];
  sandbox_modes: string[];
  worker_tools: { name: string; version: number }[];
  tool_permissions: string[];
  installed_models: { runtime: string; identifier: string }[];
  model_deployments: Deployment[];
}
export interface Deployment {
  disk_bytes?: number | null;
  metadata_source?: "provider_reported" | "configured";
  connection_id?: string | null;
  shared_inference_group_id?: string | null;
  digest?: string | null;
  identifier: string;
  provider: string;
  provider_id: string;
  available: boolean;
  verified_capabilities: string[];
  declared_capabilities: string[];
  operations: string[];
  context_window: number | null;
  estimated_ram_bytes: number | null;
  estimated_vram_bytes: number | null;
}
export interface ModelInfo {
  node_name?: string;
  workspace_allowed?: boolean;
  can_enable?: boolean;
  worker_available?: boolean;
  grant_id?: string | null;
  node_id: string;
  owner_id: string;
  state: string;
  available: boolean;
  deployment: Deployment;
}
export interface JobInfo {
  execution?: {
    attempt_id: string;
    attempt_number: number;
    node_id: string;
    node_name: string | null;
    owner_id: string | null;
    owner_name: string | null;
    can_inspect_node: boolean;
  } | null;
  owner_name?: string | null;
  owner_picture?: string | null;
  input?: Record<string, Json>;
  id: string;
  owner_id: string;
  workspace_id: string;
  type: string;
  status: string;
  priority: number;
  assigned_node_id: string | null;
  current_attempt_id: string | null;
  attempt_count: number;
  fencing_token: number;
  checkpoint_ref: string | null;
  cancel_requested_at: string | null;
  next_run_at: string | null;
  requirements: Record<string, Json>;
  result: Json;
  created_at: string;
  retry: { limit: number; backoff_seconds: number };
}
export interface AgentInfo {
  id: string;
  version_id: string;
  version: number;
  enabled: boolean;
  owner_id: string;
  workspace_id: string;
  definition: {
    name: string;
    description: string;
    requirements: Record<string, Json>;
    allowed_tools: { name: string; version: number }[];
    permissions: string[];
    workflow: {
      id: string;
      version: number;
      steps: {
        id: string;
        kind: string;
        instruction?: string;
        output_schema?: string;
        input_step?: string | null;
        tool?: { name: string; version: number } | null;
        timeout_seconds?: number;
        parameters?: Record<string, Json>;
      }[];
    };
  };
}
export interface AuditEvent {
  actor_name?: string | null;
  actor_picture?: string | null;
  id: string;
  type: string;
  created_at: string;
  actor_id: string | null;
  workspace_id: string | null;
  job_id: string | null;
  node_id: string | null;
  attempt_id: string | null;
  severity: string;
  details: Record<string, Json>;
}
export interface EventPage {
  items: AuditEvent[];
  total: number;
  offset: number;
  limit: number;
}
export interface Snapshot {
  release?: {
    version: string | null;
    revision: string | null;
    built_at: string | null;
  };
  environment: "local" | "test" | "production";
  generated_at: string;
  actor_id: string;
  workspace_id: string | null;
  workspaces: {
    id: string;
    name: string;
    owner_id: string;
    can_manage: boolean;
  }[];
  node_counts: Record<string, number>;
  job_counts: Record<string, number>;
  agent_counts: {
    enabled_versions: number;
    disabled_versions: number;
    active_versions: number;
    compatible_online_versions: number | null;
  };
  nodes: NodeInfo[];
  jobs: JobInfo[];
  agents: AgentInfo[];
  models: ModelInfo[];
  events: EventPage;
  totals: { nodes: number; jobs: number; agents: number };
  limit: number;
  offset: number;
  metrics: {
    recent_measurements?: {
      measurement_id: string;
      source: "inference_attempt" | "workflow_step";
      attempt_id: string;
      job_id: string;
      node_id: string;
      step_id: string | null;
      measured_at: string;
      deployment: Deployment | null;
      usage: InferenceUsage | null;
    }[];
    recent_attempts: {
      attempt_id: string;
      node_id: string;
      status: string;
      deployment?: Deployment | null;
      usage: InferenceUsage | null;
    }[];
  } | null;
}
export interface InferenceUsage {
  duration_seconds?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  first_token_seconds?: number | null;
  tokens_per_second?: number | null;
  token_source?: string;
  rate_source?: string;
  timing_source?: string;
}
export interface AttemptInfo {
  started_at?: string | null;
  id: string;
  number: number;
  node_id: string;
  status: string;
  fencing_token: number;
  created_at: string;
  finished_at: string | null;
  recovered_from_attempt_id: string | null;
  resumed_checkpoint_version: number;
  error: Record<string, Json>;
}
export interface CheckpointInfo {
  id: string;
  version: number;
  attempt_id: string;
  created_at: string;
  artifact: { id: string; checksum: string; size_bytes: number };
}
export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}
export interface JobDetail {
  context?: {
    agent_name: string | null;
    workspace_name: string;
    node_name: string | null;
    coding: boolean;
    apply_enabled?: boolean;
    apply_reason?: string | null;
  };
  result_action?: { job_id: string; status: string; result: Json } | null;
  can_control: boolean;
  job: JobInfo;
  attempts: AttemptInfo[];
  workflow: {
    status: string;
    current_step: number;
    checkpoint_version: number;
    recovery_error: string | null;
    agent_id: string;
    agent_version: number;
  } | null;
  checkpoints: CheckpointInfo[];
  steps: {
    id: string;
    step_id: string;
    attempt_id: string;
    status: string;
    error_code: string | null;
    output_artifact_id: string | null;
    metadata: Json;
  }[];
  events: EventPage;
  output: Json;
}
export interface NodeDetail {
  can_control: boolean;
  node: NodeInfo;
  jobs: JobInfo[];
  events: EventPage;
}
export type Section =
  "overview" | "jobs" | "nodes" | "agents" | "models" | "activity";

export function short(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : "—";
}
export function bytes(value: number | null | undefined): string {
  return value == null
    ? "Unavailable"
    : `${(value / 1024 ** 3).toFixed(1)} GiB`;
}
export function localTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Unavailable";
}
export function retryEligible(detail: JobDetail): boolean {
  const last = detail.attempts.at(-1);
  return (
    detail.job.type !== "result.action" &&
    !(
      detail.job.requirements?.model_selection as
        Record<string, Json> | undefined
    )?.connection_id &&
    detail.job.status === "FAILED" &&
    detail.job.attempt_count < 11 &&
    !detail.job.cancel_requested_at &&
    detail.workflow?.status !== "REVIEW_REQUIRED" &&
    !!last &&
    [
      "lease_expired",
      "timeout",
      "transient_error",
      "provider_unavailable",
      "provider_timeout",
      "rate_limited",
      "step_timeout",
    ].includes(String(last.error.code))
  );
}
