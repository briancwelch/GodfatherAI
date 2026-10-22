"use client";

import { BulkTable } from "./bulk-table";

import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import { control } from "../lib/control-client";
import type {
  AgentInfo,
  EventPage,
  JobInfo,
  Json,
  ModelInfo,
  Snapshot,
} from "../lib/contracts";
import {
  ConfirmAction,
  DataTable,
  EventTimeline,
  JsonDetails,
  StatusBadge,
} from "./operational";
import { RibbonGroup, UnavailableCommand } from "./application-shell";

interface Tool {
  reference: { name: string; version: number };
  permissions: string[];
  side_effect: string;
}
interface Options {
  capabilities: string[];
  models: ModelInfo[];
  tools: Tool[];
  workflows: { id: string; name: string; output_schema: string }[];
  model_limit: number;
  repositories: {
    id: string;
    name: string;
    node_name: string;
    available: boolean;
  }[];
}
const modelKey = (m: ModelInfo) =>
  `${m.deployment.provider}:${m.deployment.identifier}${m.deployment.connection_id ? `:${m.deployment.connection_id}` : ""}`;
const key = (tool: { name: string; version: number }) =>
  `${tool.name}@${tool.version}`;
const subscribeRibbon = () => () => {};
const ribbonHost = () => document.getElementById("section-ribbon");
const serverRibbon = () => null;

export function AgentManagement({
  data,
  refresh,
  initialModel,
}: {
  data: Snapshot;
  refresh: () => void;
  initialModel?: string;
}) {
  const [selectedId, setSelectedId] = useState("");
  const host = useSyncExternalStore(subscribeRibbon, ribbonHost, serverRibbon);
  const selected = data.agents.find((a) => a.version_id === selectedId);
  const [options, setOptions] = useState<Options | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<AgentInfo | "new" | null>(() =>
    initialModel &&
    data.workspaces.some((w) => w.id === data.workspace_id && w.can_manage)
      ? "new"
      : null,
  );
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<{
    events: EventPage;
    assignments: unknown[];
    jobs: JobInfo[];
  } | null>(null);
  const manage = data.workspaces.find(
    (w) => w.id === data.workspace_id,
  )?.can_manage;
  useEffect(() => {
    let active = true;
    if (data.workspace_id)
      void control<Options>(`agent-options?workspace_id=${data.workspace_id}`)
        .then((result) => {
          if (active) {
            setOptions(result);
            setError("");
          }
        })
        .catch((e) => {
          if (active) {
            setOptions(null);
            setError(e.message);
          }
        });
    return () => {
      active = false;
    };
  }, [data.workspace_id, data.generated_at]);
  useEffect(() => {
    let active = true;
    async function load() {
      if (!selected) return;
      try {
        const result = await control<NonNullable<typeof history>>(
          `command-center/agents/${selected.id}`,
        );
        if (active) {
          setHistory(result);
          setError("");
        }
      } catch (e) {
        if (active) {
          setHistory(null);
          setError(e instanceof Error ? e.message : "History unavailable");
        }
      }
    }
    void load();
    const timer = setInterval(load, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selected, data.workspace_id]);
  const editReason = !manage
    ? "Workspace administration required"
    : !selected
      ? "Select an agent version"
      : "";
  const commands = (
    <div className="context-ribbon" aria-label="Agent commands">
      <RibbonGroup label="Definitions">
        {manage && options ? (
          <button
            className="action secondary"
            onClick={() => setEditing("new")}
          >
            Create agent
          </button>
        ) : (
          <UnavailableCommand
            label="Create agent"
            reason={
              !manage
                ? "Workspace administration required"
                : "Waiting for backend catalog"
            }
          />
        )}
        {editReason ? (
          <UnavailableCommand label="Edit / New version" reason={editReason} />
        ) : (
          <button
            className="action secondary"
            onClick={() => selected && setEditing(selected)}
          >
            Edit / New version
          </button>
        )}
      </RibbonGroup>
      <RibbonGroup label="Availability">
        {selected && manage ? (
          <ConfirmAction
            label={selected.enabled ? "Disable agent" : "Enable agent"}
            description="Change availability for this pinned version. Disabling prevents new step starts; existing committed work remains. Cancel a job to stop execution."
            onConfirm={async () => {
              await control(
                `agents/${selected.id}/versions/${selected.version}/control`,
                { action: selected.enabled ? "disable" : "enable" },
              );
              refresh();
            }}
          />
        ) : (
          <UnavailableCommand label="Enable / Disable" reason={editReason} />
        )}
      </RibbonGroup>
      <RibbonGroup label="Execution">
        {selected?.enabled ? (
          <button className="action" onClick={() => setRunning(true)}>
            Run agent
          </button>
        ) : (
          <UnavailableCommand
            label="Run agent"
            reason={
              selected
                ? "Enable this version before running"
                : "Select an enabled agent version"
            }
          />
        )}
      </RibbonGroup>
    </div>
  );
  return (
    <>
      {host ? createPortal(commands, host) : commands}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <div className={selected ? "record-split" : ""}>
        <BulkTable
          kind="agents"
          scope={`${data.workspace_id}:${data.offset}:${data.agents.map((a) => a.version_id).join()}`}
          deleteKey={(a) => a.id}
          label={(a) => `agent ${a.definition.name}, all versions`}
          eligible={() => !!manage}
          onDeleted={() => {
            setSelectedId("");
            refresh();
          }}
          caption="Agents and immutable versions"
          rows={data.agents}
          rowKey={(a) => a.version_id}
          selectedKey={selectedId}
          onSelect={(a) => {
            setHistory(null);
            setSelectedId(a.version_id);
          }}
          columns={[
            {
              label: "Agent",
              cell: (a) => (
                <button
                  className="text-button"
                  aria-pressed={selectedId === a.version_id}
                  onClick={() => {
                    setHistory(null);
                    setSelectedId(a.version_id);
                  }}
                >
                  {a.definition.name}
                </button>
              ),
            },
            { label: "Version", cell: (a) => `v${a.version}` },
            {
              label: "State",
              cell: (a) => (
                <StatusBadge value={a.enabled ? "enabled" : "disabled"} />
              ),
            },
            {
              label: "Model",
              cell: (a) =>
                String(
                  (
                    a.definition.requirements.model_selection as
                      Record<string, Json> | undefined
                  )?.identifier || "Capability selection",
                ),
            },
            {
              label: "Tools / steps",
              cell: (a) => (
                <>
                  {a.definition.allowed_tools.map(key).join(", ") || "No tools"}
                  <small>
                    {a.definition.workflow.steps.length} workflow steps
                  </small>
                </>
              ),
            },
          ]}
        />
        {selected && (
          <aside
            className="panel record-inspector"
            aria-label="Agent inspector"
          >
            <div className="actions">
              <h2>
                {selected.definition.name} · v{selected.version}
              </h2>
              <button
                className="action secondary"
                onClick={() => setSelectedId("")}
              >
                Close inspector
              </button>
            </div>
            <p>{selected.definition.description || "No description."}</p>
            <small>
              Agent {selected.id} · Owner {selected.owner_id}
            </small>
            <JsonDetails
              label="Immutable configuration"
              value={selected.definition}
            />
            <h3>Execution history and results</h3>
            {!history ? (
              <p role="status">Loading execution history…</p>
            ) : (
              <>
                <DataTable
                  caption="Recent agent runs"
                  rows={history.jobs || []}
                  rowKey={(j) => j.id}
                  columns={[
                    {
                      label: "Job",
                      cell: (j) => (
                        <a href={`/jobs/${j.id}`}>{j.id.slice(0, 8)}</a>
                      ),
                    },
                    {
                      label: "Progress",
                      cell: (j) => <StatusBadge value={j.status} />,
                    },
                    {
                      label: "Results",
                      cell: (j) => (
                        <a href={`/jobs/${j.id}`}>Progress / results</a>
                      ),
                    },
                  ]}
                />
                <EventTimeline events={history.events.items} />
              </>
            )}
          </aside>
        )}
      </div>
      {editing && options && (
        <AgentEditor
          key={editing === "new" ? "new" : editing.version_id}
          initial={editing === "new" ? undefined : editing}
          data={data}
          options={options}
          initialModel={initialModel}
          close={() => setEditing(null)}
          saved={(a) => {
            setSelectedId(a.version_id);
            setEditing(null);
            refresh();
          }}
        />
      )}
      {running && selected && (
        <RunAgent agent={selected} close={() => setRunning(false)} />
      )}
    </>
  );
}

function AgentEditor({
  initial,
  data,
  options,
  close,
  saved,
  initialModel,
}: {
  initial?: AgentInfo;
  data: Snapshot;
  options: Options;
  close: () => void;
  saved: (a: AgentInfo) => void;
  initialModel?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const firstStep = initial?.definition.workflow.steps[0];
  const simpleWorkflow =
    !initial ||
    (["model", "coding"].includes(firstStep?.kind || "") &&
      ["text", "plan", "coding"].includes(firstStep?.output_schema || "") &&
      initial.definition.workflow.steps
        .slice(1)
        .every((s) => s.kind === "tool" && s.input_step === firstStep?.id));
  const [workflow, setWorkflow] = useState(
    simpleWorkflow ? firstStep?.output_schema || "text" : "custom",
  );
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const models = [
    ...new Map(options.models.map((m) => [modelKey(m), m])).values(),
  ];
  const existingSelection = initial?.definition.requirements.model_selection as
    Record<string, Json> | undefined;
  const existingModel = existingSelection?.identifier
    ? `${existingSelection.provider || ""}:${existingSelection.identifier}${existingSelection.connection_id ? `:${existingSelection.connection_id}` : ""}`
    : "";
  const [modelChoice, setModelChoice] = useState(
    existingModel || initialModel || (models[0] ? modelKey(models[0]) : ""),
  );
  const paid = !!(
    models.find((m) => modelKey(m) === modelChoice)?.deployment.connection_id ||
    (modelChoice === existingModel && existingSelection?.connection_id)
  );
  const chosenOwner = models.find((m) => modelKey(m) === modelChoice)?.owner_id;
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const chosen = models.find((m) => modelKey(m) === form.get("model"));
      const tools = options.tools.filter((t) =>
        form.getAll("tools").includes(key(t.reference)),
      );
      const permissions = [...new Set(tools.flatMap((t) => t.permissions))];
      if (workflow === "coding") permissions.push("coding.workspace");
      let steps: Record<string, unknown>[];
      if (workflow === "custom") steps = JSON.parse(String(form.get("steps")));
      else {
        steps = [
          {
            id: "response",
            kind: workflow === "coding" ? "coding" : "model",
            instruction: String(form.get("instruction")),
            output_schema: workflow,
            timeout_seconds: Number(form.get("step_timeout")),
            parameters: { max_tokens: Number(form.get("max_tokens")) },
          },
        ];
        if (workflow === "plan")
          for (const [index, tool] of tools.entries())
            steps.push({
              id: `summary-${index + 1}`,
              kind: "tool",
              input_step: "response",
              tool: tool.reference,
              output_schema: "plan_summary",
            });
      }
      const definition = {
        ...(initial?.definition || {}),
        name: String(form.get("name")),
        description: String(form.get("description")),
        enabled: form.get("enabled") === "on",
        requirements: {
          ...(initial?.definition.requirements || {}),
          capabilities: form.getAll("capabilities"),
          runtimes: workflow === "coding" ? ["coding-sandbox-v1"] : [],
          model_selection: chosen
            ? {
                ...existingSelection,
                identifier: chosen.deployment.identifier,
                provider: chosen.deployment.provider,
                connection_id: chosen.deployment.connection_id || null,
                paid_consent:
                  !!chosen.deployment.connection_id &&
                  form.get("paid") === "on",
                grant_id: form.get("grant") || chosen.grant_id || null,
                fallback_models:
                  chosen.deployment.provider === "ollama"
                    ? String(form.get("fallbacks") || "")
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean)
                    : [],
                required_operations:
                  chosen.deployment.connection_id &&
                  ["plan", "coding"].includes(workflow)
                    ? ["structured_output"]
                    : [],
              }
            : existingSelection,
        },
        allowed_tools: tools.map((t) => t.reference),
        permissions,
        retry: {
          limit: workflow === "coding" || paid ? 0 : 1,
          backoff_seconds: 1,
        },
        workflow: {
          id: initial?.definition.workflow.id || crypto.randomUUID(),
          version: (initial?.definition.workflow.version || 0) + 1,
          steps,
        },
      };
      const result = await control<AgentInfo>(
        initial ? `agents/${initial.id}/versions` : "agents",
        initial
          ? { expected_version: initial.version, definition }
          : { workspace_id: String(form.get("workspace")), definition },
      );
      saved(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save not confirmed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="agent-dialog"
      aria-label={initial ? "Create immutable agent version" : "Create agent"}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) close();
      }}
    >
      <form onSubmit={submit}>
        <h2>
          {initial
            ? `Edit ${initial.definition.name} · save as a new immutable version`
            : "Create agent"}
        </h2>
        <p className="muted">
          Existing versions and running jobs retain their pinned configuration.
        </p>
        <div className="form-grid">
          <label>
            Name
            <input
              name="name"
              defaultValue={initial?.definition.name}
              required
              maxLength={200}
              autoFocus
            />
          </label>
          <label>
            Workspace
            <select
              name="workspace"
              defaultValue={initial?.workspace_id || data.workspace_id || ""}
              disabled={!!initial}
              required
            >
              {data.workspaces
                .filter(
                  (w) =>
                    w.can_manage &&
                    w.id === (initial?.workspace_id || data.workspace_id),
                )
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
            </select>
            <small>
              Select the target workspace in the command bar before creating an
              agent.
            </small>
          </label>
          <label className="full-width">
            Description
            <textarea
              name="description"
              aria-label="Description"
              maxLength={2000}
              defaultValue={initial?.definition.description}
              rows={2}
            />
          </label>
          <label>
            Model requirement
            <select
              name="model"
              aria-label="Model requirement"
              value={modelChoice}
              onChange={(e) => setModelChoice(e.target.value)}
              required={!existingSelection}
            >
              {!models.length && !existingSelection && (
                <option value="">No permitted models advertised</option>
              )}
              {existingSelection &&
                !models.some((m) => modelKey(m) === existingModel) && (
                  <option value={existingModel}>
                    Preserve existing model requirement
                  </option>
                )}
              {models.map((m) => (
                <option key={modelKey(m)} value={modelKey(m)}>
                  {m.deployment.identifier} · {m.deployment.provider}
                  {m.available ? "" : " · unavailable"}
                  {m.deployment.connection_id
                    ? ` · paid connection ${m.deployment.connection_id.slice(0, 8)}`
                    : " · local"}
                </option>
              ))}
            </select>
            <small>
              First {options.model_limit} permitted advertisements. Execution
              waits for a compatible worker.
            </small>
          </label>
          {paid && (
            <>
              <label className="check-label">
                <input type="checkbox" name="paid" required /> Allow this agent
                to request paid API inference and send task data to the selected
                provider. Each run requires confirmation.
              </label>
              {chosenOwner && chosenOwner !== data.actor_id && (
                <label>
                  Owner-issued access grant (shared connection)
                  <input
                    name="grant"
                    defaultValue={String(existingSelection?.grant_id || "")}
                  />
                </label>
              )}
              <p>
                Billing and spending limits are managed in the provider account.{" "}
                <a href="/providers">Manage AI connections</a>.
              </p>
            </>
          )}
          <label>
            Approved local fallback models (comma separated)
            <input
              name="fallbacks"
              disabled={paid}
              defaultValue={
                Array.isArray(existingSelection?.fallback_models)
                  ? existingSelection.fallback_models.join(", ")
                  : ""
              }
            />
            <small>
              Only exact Ollama models allowed by this workspace. Paid fallback
              remains unavailable.
            </small>
          </label>
          <label>
            Supported workflow
            <select
              value={workflow}
              onChange={(e) => setWorkflow(e.target.value)}
            >
              {options.workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
              <option value="custom">
                Custom sequential steps (runtime v1)
              </option>
            </select>
          </label>
          <fieldset>
            <legend>Required capabilities</legend>
            {[
              ...new Set([
                ...options.capabilities,
                ...((initial?.definition.requirements
                  .capabilities as string[]) || []),
              ]),
            ].map((c) => (
              <label className="check-label" key={c}>
                <input
                  type="checkbox"
                  name="capabilities"
                  value={c}
                  defaultChecked={(
                    (initial?.definition.requirements
                      .capabilities as string[]) || []
                  ).includes(c)}
                />
                {c}
              </label>
            ))}
            {!options.capabilities.length && (
              <small>
                No capability advertisements. Exact model selection still
                applies.
              </small>
            )}
          </fieldset>
          <fieldset>
            <legend>Authorized read-only tools</legend>
            {options.tools.map((t) => (
              <label className="check-label" key={key(t.reference)}>
                <input
                  type="checkbox"
                  name="tools"
                  value={key(t.reference)}
                  defaultChecked={initial?.definition.allowed_tools.some(
                    (r) => key(r) === key(t.reference),
                  )}
                />
                {key(t.reference)}
                <small>{t.permissions.join(", ")}</small>
              </label>
            ))}
            {!options.tools.length && (
              <small>No tools permitted by this workspace.</small>
            )}
            <small>
              Plan workflows run selected tools after the model step. Node-owner
              grants are checked at execution.
            </small>
          </fieldset>
          {workflow === "custom" ? (
            <label className="full-width">
              Sequential workflow steps (JSON)
              <textarea
                name="steps"
                defaultValue={JSON.stringify(
                  initial?.definition.workflow.steps || [],
                  null,
                  2,
                )}
                rows={10}
                required
              />
              <small>
                Model outputs: text or plan. Tool outputs: plan_summary with a
                prior plan input. Validated by runtime v1.
              </small>
            </label>
          ) : (
            <label className="full-width">
              Model step instruction
              <textarea
                name="instruction"
                rows={4}
                required
                maxLength={4096}
                defaultValue={
                  initial?.definition.workflow.steps[0]?.instruction ||
                  "Respond to the user's instruction accurately and clearly."
                }
              />
            </label>
          )}
          {workflow !== "custom" && (
            <>
              <label>
                Maximum output tokens
                <input
                  name="max_tokens"
                  type="number"
                  min={1}
                  max={8192}
                  defaultValue={Number(
                    firstStep?.parameters?.max_tokens || 2048,
                  )}
                  required
                />
              </label>
              <label>
                Step timeout (seconds)
                <input
                  name="step_timeout"
                  type="number"
                  min={1}
                  max={3600}
                  defaultValue={firstStep?.timeout_seconds || 240}
                  required
                />
              </label>
            </>
          )}
          <label className="check-label">
            <input
              type="checkbox"
              name="enabled"
              defaultChecked={initial?.enabled ?? true}
            />
            Enabled for new runs
          </label>
        </div>
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
            onClick={close}
          >
            Cancel
          </button>
          <button
            className="action"
            disabled={busy || (!models.length && !existingSelection)}
          >
            {busy ? "Saving…" : initial ? "Save new version" : "Create agent"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

function RunAgent({ agent, close }: { agent: AgentInfo; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      aria-label="Run agent"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) close();
      }}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          const form = new FormData(e.currentTarget);
          try {
            const job = await control<JobInfo>("workflow/jobs", {
              workspace_id: agent.workspace_id,
              agent_id: agent.id,
              agent_version: agent.version,
              input: {
                instruction: form.get("instruction"),
                repository_id: form.get("repository_id") || null,
                search_terms: String(form.get("code_search") || "")
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              },
              paid_consent: form.get("paid_consent") === "on",
              priority: Number(form.get("priority")),
            });
            window.location.assign(`/jobs/${job.id}`);
          } catch (e) {
            setError(
              e instanceof Error ? e.message : "Submission not confirmed",
            );
            setBusy(false);
          }
        }}
      >
        <h2>
          Run {agent.definition.name} · v{agent.version}
        </h2>
        <p>
          Submit to the existing scheduler. A compatible authorized workflow
          worker must be available.
        </p>
        {agent.definition.workflow.steps.some((s) => s.kind === "coding") && (
          <RepositorySelection workspace={agent.workspace_id} />
        )}
        {!!(
          agent.definition.requirements.model_selection as Record<string, Json>
        )?.connection_id && (
          <label className="check-label">
            <input type="checkbox" name="paid_consent" required /> I authorize
            using my selected API account and sending this task to the provider.
            Billing and spending limits are managed at the provider.
          </label>
        )}
        <label>
          Instruction
          <textarea
            name="instruction"
            required
            maxLength={4096}
            rows={5}
            autoFocus
          />
        </label>
        <label>
          Priority
          <input
            type="number"
            name="priority"
            defaultValue={0}
            min={-100}
            max={100}
            required
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <div className="actions">
          <button
            type="button"
            className="action secondary"
            disabled={busy}
            onClick={close}
          >
            Cancel
          </button>
          <button className="action" disabled={busy}>
            {busy ? "Submitting…" : "Submit run"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

export function RepositorySelection({ workspace }: { workspace: string }) {
  const [repositories, setRepositories] = useState<
    { id: string; name: string; node_name: string; available: boolean }[]
  >([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void control<typeof repositories>(
      `coding/repositories?workspace_id=${workspace}`,
    )
      .then((rows) => {
        if (active) setRepositories(rows);
      })
      .catch(() => {
        if (active) setError("Repository access unavailable");
      });
    return () => {
      active = false;
    };
  }, [workspace]);
  return (
    <>
      <label>
        Owner-approved repository
        <select name="repository_id" required>
          <option value="">
            {error ||
              (repositories.length
                ? "Select a repository"
                : "No permitted coding repositories advertised")}
          </option>
          {repositories.map((r) => (
            <option key={`${r.id}:${r.node_name}`} value={r.id}>
              {r.name} · {r.node_name}
              {r.available ? "" : " · offline"}
            </option>
          ))}
        </select>
        <small>
          Only committed, approved files enter a disposable workspace. Network
          access is disabled. Push and deployment are unavailable.
        </small>
      </label>
      <label>
        Code search terms (optional, comma separated)
        <input name="code_search" maxLength={1024} />
        <small>
          Literal matches in approved committed files are supplied to the agent.
        </small>
      </label>
    </>
  );
}
