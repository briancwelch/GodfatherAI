"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApplicationShell, RibbonGroup } from "./application-shell";
import { ConfirmAction, JsonDetails } from "./operational";
import { control } from "../lib/control-client";
import type { Json, Snapshot } from "../lib/contracts";

interface Connection {
  id: string;
  name: string;
  owner_id: string;
  node_id: string;
  provider: string;
  available: boolean;
  revoked: boolean;
  policy: Record<string, Json>;
  models: { identifier: string; operations: string[] }[];
  estimated_microusd: number;
  reserved_microusd: number;
  test: Record<string, Json>;
  check_supported: boolean;
}
const money = (value: number) => `$${(value / 1000000).toFixed(6)} USD`;

export default function ProviderConnections({
  user,
}: {
  user: { id: string; display_name: string; roles: string[] };
}) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("");
  const [usage, setUsage] = useState<Json>(null);
  const [grants, setGrants] = useState<
    { id: string; revoked: boolean; scope: Record<string, Json> }[]
  >([]);
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision((r) => r + 1);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [snapshot, rows] = await Promise.all([
          control<Snapshot>("command-center?section=nodes"),
          control<Connection[]>("provider-connections"),
        ]);
        if (active) {
          setData(snapshot);
          setConnections(rows);
          setError("");
        }
      } catch (e) {
        if (active) {
          setError(
            e instanceof Error ? e.message : "Provider connections unavailable",
          );
          setConnections([]);
        }
      }
    };
    void load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [revision]);
  useEffect(() => {
    let active = true;
    if (selected)
      void Promise.all([
        control<Json>(`provider-connections/${selected}/usage`),
        control<typeof grants>(`provider-connections/${selected}/grants`),
      ])
        .then(([u, g]) => {
          if (active) {
            setUsage(u);
            setGrants(g);
          }
        })
        .catch(() => {
          if (active) {
            setUsage(null);
            setGrants([]);
          }
        });
    return () => {
      active = false;
    };
  }, [selected, revision]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const row = await control<{ id: string }>("provider-connections", {
        name: form.get("name"),
        node_id: form.get("node"),
        provider: form.get("provider"),
      });
      setSelected(row.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Creation failed");
    } finally {
      setBusy(false);
    }
  }
  async function save(event: FormEvent<HTMLFormElement>, row: Connection) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await control(`provider-connections/${row.id}/policy`, {
        ...row.policy,
        enabled: form.get("enabled") === "on",
        sharing: form.get("sharing"),
        default_model: form.get("default_model") || null,
        lifetime_limit_microusd: Math.round(
          Number(form.get("lifetime")) * 1000000,
        ),
        call_limit_microusd: Math.round(Number(form.get("call")) * 1000000),
        allowed_user_ids: String(form.get("users"))
          .split(/[,\s]+/)
          .filter(Boolean),
        allowed_workspace_ids: String(form.get("workspaces"))
          .split(/[,\s]+/)
          .filter(Boolean),
        rates: form.getAll("price-model").map((model, index) => ({
          identifier: String(model),
          input_microusd_per_million: Math.round(
            Number(form.getAll("price-input")[index]) * 1000000,
          ),
          output_microusd_per_million: Math.round(
            Number(form.getAll("price-output")[index]) * 1000000,
          ),
          source: String(form.getAll("price-source")[index]),
          verified_at: new Date(
            `${String(form.getAll("price-date")[index])}T00:00:00Z`,
          ).toISOString(),
        })),
      });
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Policy rejected");
    } finally {
      setBusy(false);
    }
  }
  const row = connections.find((c) => c.id === selected);
  return (
    <ApplicationShell
      section="providers"
      data={data}
      account={user}
      stale={!!error}
      refresh={refresh}
      ribbon={
        <RibbonGroup label="Provider connections">
          <a className="action secondary" href="#add-provider">
            Add connection
          </a>
          <a className="action secondary" href="/models">
            Models
          </a>
        </RibbonGroup>
      }
    >
      <main id="main-content" className="provider-page">
        <h1>Provider Connections</h1>
        <p>
          Google Sign-In authenticates your Godfather account. OpenAI and
          Anthropic API keys separately authorize paid inference. API keys
          remain on your worker.
        </p>
        <p className="notice">
          Private by default. No paid fallback or automatic paid retries. Limits
          and costs below are application safeguards and estimates, not provider
          billing caps or invoices.
        </p>
        {error && <p role="alert">{error}</p>}
        {!data && (
          <p role="status">Loading authorized workers and connections…</p>
        )}
        <section id="add-provider" className="panel">
          <h2>Add provider connection</h2>
          <form onSubmit={create} className="form-grid">
            <label>
              Name
              <input name="name" required maxLength={100} />
            </label>
            <label>
              Provider
              <select name="provider">
                <option value="openai">OpenAI API</option>
                <option value="anthropic">Anthropic API</option>
              </select>
            </label>
            <label>
              Owned worker
              <select name="node" required>
                {data?.nodes
                  .filter((n) => n.owner_id === user.id)
                  .map((n) => (
                    <option key={n.node_id} value={n.node_id}>
                      {n.name} · {n.os}
                    </option>
                  ))}
              </select>
            </label>
            <button
              className="action"
              disabled={
                busy || !data?.nodes.some((n) => n.owner_id === user.id)
              }
            >
              Create private connection
            </button>
          </form>
        </section>
        <div className="record-split">
          <section className="panel">
            <h2>Your connections</h2>
            {!connections.length && data && (
              <p>
                No provider connections. Local Ollama inference remains
                available through Models.
              </p>
            )}
            {connections.map((c) => (
              <p key={c.id}>
                <button
                  className="action secondary"
                  aria-pressed={c.id === selected}
                  onClick={() => {
                    setUsage(null);
                    setSelected(c.id);
                  }}
                >
                  {c.name} · {c.provider}
                </button>
                <small>
                  {c.revoked
                    ? "Revoked"
                    : c.available
                      ? "Worker model inventory available"
                      : "Unavailable: configure and start the worker"}{" "}
                  ·{" "}
                  {c.policy.enabled ? "Paid use enabled" : "Paid use disabled"}
                </small>
              </p>
            ))}
          </section>
          {row && (
            <section className="panel" key={row.id}>
              <h2>{row.name}</h2>
              <p>
                Connection <code>{row.id}</code> · payer{" "}
                <code>{row.owner_id}</code>
              </p>
              <h3>Secure local credential setup</h3>
              <p>
                Run on the selected worker under your own OS account. Enter the
                API key at the hidden prompt. Google tokens, consumer
                subscriptions and machine credentials cannot be used here.
              </p>
              <pre>{`godfather-worker provider set ${row.provider} ${row.id}`}</pre>
              <p>
                Add this connection ID and provider to that worker&apos;s
                inference configuration, select its allowed model catalog, then
                restart it. <a href="/models">Model availability</a> is based on
                worker discovery.
              </p>
              <button
                className="action secondary"
                disabled={busy || row.revoked || !row.check_supported}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await control(`provider-connections/${row.id}/test`, {});
                    refresh();
                  } catch (e) {
                    setError(e instanceof Error ? e.message : "Test failed");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Test connection without inference
              </button>
              <p role="status">
                Last connection check:{" "}
                {String(row.test?.status || "Not tested")}
                {row.test?.checked_at
                  ? ` · ${new Date(String(row.test.checked_at)).toLocaleString()}`
                  : ""}
              </p>
              {!row.check_supported && (
                <p>
                  Configure this provider connection on its worker and restart
                  it to enable connection checks.
                </p>
              )}
              <p>
                Models:{" "}
                {row.models
                  .map((m) => `${m.identifier} (${m.operations.join(", ")})`)
                  .join("; ") || "No supported models advertised"}
              </p>
              <form onSubmit={(e) => save(e, row)}>
                <fieldset disabled={busy || row.revoked}>
                  <legend>Permissions and spending safeguards</legend>
                  <label>
                    <input
                      type="checkbox"
                      name="enabled"
                      defaultChecked={row.policy.enabled === true}
                    />{" "}
                    Enable explicitly authorized paid calls
                  </label>
                  <label>
                    Sharing
                    <select
                      name="sharing"
                      defaultValue={String(row.policy.sharing)}
                    >
                      <option value="private">Private</option>
                      <option value="approval_required">
                        Shared with per-job approval
                      </option>
                      <option value="limited">Shared with scoped limits</option>
                    </select>
                  </label>
                  <label>
                    Default model
                    <input
                      name="default_model"
                      list={`provider-models-${row.id}`}
                      defaultValue={String(row.policy.default_model || "")}
                    />
                  </label>
                  <label>
                    Lifetime safeguard (USD)
                    <input
                      name="lifetime"
                      type="number"
                      min="0"
                      step="0.000001"
                      defaultValue={
                        Number(row.policy.lifetime_limit_microusd || 0) /
                        1000000
                      }
                      required
                    />
                  </label>
                  <label>
                    Per-call safeguard (USD)
                    <input
                      name="call"
                      type="number"
                      min="0"
                      step="0.000001"
                      defaultValue={
                        Number(row.policy.call_limit_microusd || 0) / 1000000
                      }
                      required
                    />
                  </label>
                  <label>
                    Allowed borrower user UUIDs
                    <input
                      name="users"
                      defaultValue={
                        Array.isArray(row.policy.allowed_user_ids)
                          ? row.policy.allowed_user_ids.join(", ")
                          : ""
                      }
                    />
                  </label>
                  <label>
                    Allowed workspace UUIDs
                    <input
                      name="workspaces"
                      defaultValue={
                        Array.isArray(row.policy.allowed_workspace_ids)
                          ? row.policy.allowed_workspace_ids.join(", ")
                          : ""
                      }
                    />
                  </label>
                  <ModelPrices connection={row} />
                  <button className="action">Save policy</button>
                </fieldset>
              </form>
              <h3>Usage</h3>
              {typeof row.policy.default_model === "string" &&
                data?.workspace_id && (
                  <a
                    className="action secondary"
                    href={`/agents?workspace=${data.workspace_id}&model=${encodeURIComponent(`${row.provider}:${row.policy.default_model}:${row.id}`)}`}
                  >
                    Create agent with default model
                  </a>
                )}
              <p>
                Estimated settled cost {money(row.estimated_microusd)} ·
                outstanding reservations {money(row.reserved_microusd)}.
              </p>
              <JsonDetails
                label="Per-job token usage and estimated costs"
                value={usage}
              />
              <h3>Owner-issued spending grants</h3>
              <p>
                Borrower access requires both this policy and an expiring grant.
                Per-job approval also requires the exact job UUID. Platform
                administrators cannot override these permissions.
              </p>
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  const form = new FormData(event.currentTarget);
                  setBusy(true);
                  try {
                    await control(`provider-connections/${row.id}/grants`, {
                      user_id: form.get("borrower"),
                      workspace_id: form.get("workspace"),
                      model: form.get("model"),
                      job_id: form.get("job") || null,
                      expires_at: new Date(
                        String(form.get("expiry")),
                      ).toISOString(),
                      limit_microusd: Math.round(
                        Number(form.get("limit")) * 1000000,
                      ),
                    });
                    refresh();
                  } catch (e) {
                    setError(e instanceof Error ? e.message : "Grant rejected");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label>
                  Borrower user ID
                  <input name="borrower" required />
                </label>
                <label>
                  Workspace
                  <select name="workspace" required>
                    {data?.workspaces.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Exact model ID
                  <input
                    name="model"
                    required
                    list={`provider-models-${row.id}`}
                  />
                </label>
                <label>
                  Pending job ID (required for per-job approval)
                  <input
                    name="job"
                    required={row.policy.sharing === "approval_required"}
                  />
                </label>
                <label>
                  Expires at (your local time)
                  <input name="expiry" type="datetime-local" required />
                </label>
                <label>
                  Grant spending safeguard (USD)
                  <input
                    name="limit"
                    type="number"
                    min="0.000001"
                    step="0.000001"
                    required
                  />
                </label>
                <button
                  className="action secondary"
                  disabled={busy || row.revoked}
                >
                  Issue spending grant
                </button>
              </form>
              {grants.map((g) => (
                <div key={g.id}>
                  <code>{g.id}</code>
                  <JsonDetails
                    label={g.revoked ? "Revoked grant" : "Grant scope"}
                    value={g.scope}
                  />
                  {!g.revoked && (
                    <ConfirmAction
                      label="Revoke grant"
                      description="Block new calls using this grant. Already accepted provider calls may still be billed."
                      onConfirm={async () => {
                        await control(
                          `provider-connections/${row.id}/grants/${g.id}/revoke`,
                          {},
                        );
                        refresh();
                      }}
                    />
                  )}
                </div>
              ))}
              {!row.revoked && (
                <div className="actions">
                  <ConfirmAction
                    label="Disable connection"
                    description="Prevent new paid calls without changing Google login or removing the worker-local key."
                    onConfirm={async () => {
                      await control(`provider-connections/${row.id}/control`, {
                        action: "disable",
                      });
                      refresh();
                    }}
                  />
                  <ConfirmAction
                    label="Revoke connection"
                    description="Permanently prevent new Godfather calls using this connection. Remove its key locally and revoke it at the provider separately."
                    onConfirm={async () => {
                      await control(`provider-connections/${row.id}/control`, {
                        action: "revoke",
                      });
                      refresh();
                    }}
                  />
                </div>
              )}
            </section>
          )}
        </div>
      </main>
    </ApplicationShell>
  );
}

function ModelPrices({ connection }: { connection: Connection }) {
  const [rates, setRates] = useState<Record<string, Json>[]>(
    Array.isArray(connection.policy.rates)
      ? (connection.policy.rates as Record<string, Json>[])
      : [],
  );
  const source =
    connection.provider === "openai"
      ? "https://openai.com/api/pricing/"
      : "https://platform.claude.com/docs/en/about-claude/pricing";
  return (
    <section>
      <h4>Owner-verified model pricing</h4>
      <p>
        Enter current prices from the{" "}
        <a href={source} rel="noreferrer" target="_blank">
          official provider pricing
        </a>
        . Prices are USD per million tokens. Verification expires after 30 days;
        missing prices block calls.
      </p>
      {rates.map((rate, index) => (
        <fieldset key={index}>
          <legend>Model price {index + 1}</legend>
          <label>
            Exact model ID
            <input
              name="price-model"
              required
              defaultValue={String(rate.identifier || "")}
              list={`provider-models-${connection.id}`}
            />
          </label>
          <label>
            Input USD / million tokens
            <input
              name="price-input"
              type="number"
              min="0"
              step="0.000001"
              required
              defaultValue={
                Number(rate.input_microusd_per_million || 0) / 1000000
              }
            />
          </label>
          <label>
            Output USD / million tokens
            <input
              name="price-output"
              type="number"
              min="0"
              step="0.000001"
              required
              defaultValue={
                Number(rate.output_microusd_per_million || 0) / 1000000
              }
            />
          </label>
          <label>
            Official pricing source
            <input
              name="price-source"
              type="url"
              required
              defaultValue={String(rate.source || source)}
            />
          </label>
          <label>
            Date verified against provider pricing (UTC)
            <input
              name="price-date"
              type="date"
              required
              defaultValue={
                rate.verified_at ? String(rate.verified_at).slice(0, 10) : ""
              }
            />
          </label>
          <button
            type="button"
            className="action secondary"
            onClick={() => setRates(rates.filter((_, i) => i !== index))}
          >
            Remove model price
          </button>
        </fieldset>
      ))}
      <datalist id={`provider-models-${connection.id}`}>
        {connection.models.map((m) => (
          <option key={m.identifier} value={m.identifier} />
        ))}
      </datalist>
      <button
        type="button"
        className="action secondary"
        onClick={() => setRates([...rates, {}])}
      >
        Add model price
      </button>
    </section>
  );
}
