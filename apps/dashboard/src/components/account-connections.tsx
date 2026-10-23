"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApplicationShell } from "./application-shell";
import { control } from "../lib/control-client";
import type { Snapshot } from "../lib/contracts";

interface AccountConnections {
  storage_available: boolean;
  connections: {
    provider: string;
    connected: boolean;
    models: { identifier: string }[];
    allowed_node_ids: string[];
  }[];
}

export default function AccountConnections({
  user,
}: {
  user: { id: string; display_name: string; roles: string[] };
}) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [account, setAccount] = useState<AccountConnections | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    void Promise.all([
      control<Snapshot>("command-center?section=nodes"),
      control<AccountConnections>("account/providers"),
    ])
      .then(([snapshot, connections]) => {
        if (active) {
          setData(snapshot);
          setAccount(connections);
        }
      })
      .catch(() => {
        if (active)
          setStatus("Account connections are unavailable. Try Refresh.");
      });
    return () => {
      active = false;
    };
  }, [revision]);
  async function connect(event: FormEvent<HTMLFormElement>, provider: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    if (!fields.getAll("node").length) {
      setStatus("Choose at least one of your computers for this connection.");
      return;
    }
    const input = form.elements.namedItem("api_key") as HTMLInputElement;
    const key = input.value;
    input.value = "";
    setBusy(provider);
    setStatus("Testing the connection and saving your key securely…");
    try {
      await control(`account/providers/${provider}${key ? "" : "/computers"}`, {
        ...(key ? { api_key: key } : {}),
        allowed_node_ids: fields.getAll("node"),
      });
      setStatus(
        "Connected. Enable account API connections in the selected worker app. Models appear after its next refresh.",
      );
      setRevision((r) => r + 1);
    } catch (error) {
      setStatus(
        error instanceof Error
          ? error.message
          : "Connection failed; try again.",
      );
    } finally {
      setBusy("");
    }
  }
  return (
    <ApplicationShell
      section="providers"
      data={data}
      account={user}
      refresh={() => setRevision((r) => r + 1)}
    >
      <main id="main-content" className="container-fluid provider-page">
        <h1>Account settings · AI connections</h1>
        <p>
          Connect your own OpenAI or Anthropic API account. Google Sign-In only
          signs you in to The Godfather.
        </p>
        <p>
          Your provider handles billing and spending limits. Selecting one of
          these models sends your task to that provider using your API account.
        </p>
        {status && <p role="status">{status}</p>}
        {account && !account.storage_available && (
          <p role="alert">
            Your administrator must enable encrypted account key storage before
            you can connect.
          </p>
        )}
        <div className="worker-downloads">
          {(["openai", "anthropic", "gemini"] as const).map((provider) => {
            const connection = account?.connections.find(
              (c) => c.provider === provider,
            );
            const name =
              provider === "openai"
                ? "OpenAI"
                : provider === "gemini"
                  ? "Google Gemini"
                  : "Anthropic";
            const nodes =
              data?.nodes.filter((n) => n.owner_id === user.id) ?? [];
            return (
              <section className="card panel" key={provider}>
                <h2>{name}</h2>
                <p>
                  {connection?.connected
                    ? `Connected · ${connection.models.length} supported models`
                    : "Not connected"}
                </p>
                <a
                  href={
                    provider === "openai"
                      ? "https://platform.openai.com/api-keys"
                      : provider === "gemini"
                        ? "https://aistudio.google.com/api-keys"
                        : "https://platform.claude.com/settings/keys"
                  }
                  target="_blank"
                  rel="noreferrer"
                >
                  Create an API key at {name}
                </a>
                <form
                  onSubmit={(event) => {
                    void connect(event, provider);
                  }}
                >
                  <label>
                    API key
                    <input
                      className="form-control"
                      name="api_key"
                      type="password"
                      autoComplete="off"
                      spellCheck={false}
                      required={!connection?.connected}
                      minLength={8}
                      maxLength={4096}
                      placeholder={
                        connection?.connected
                          ? "Paste a replacement key"
                          : "Paste your API key"
                      }
                    />
                  </label>
                  <fieldset>
                    <legend>Computers allowed to use this key</legend>
                    {nodes.map((node) => (
                      <label className="check-label" key={node.node_id}>
                        <input
                          className="form-check-input"
                          name="node"
                          type="checkbox"
                          value={node.node_id}
                          defaultChecked={connection?.allowed_node_ids.includes(
                            node.node_id,
                          )}
                        />
                        {node.name}
                      </label>
                    ))}
                    {!nodes.length && (
                      <p>
                        Connect your worker first using{" "}
                        <a href="/nodes">Nodes → Connect a computer</a>.
                      </p>
                    )}
                  </fieldset>
                  <p className="muted">
                    Encrypted in your account. Available only to your selected
                    computers when you enable account connections in their
                    worker app. The saved key is never shown again.
                  </p>
                  <button
                    className="btn btn-primary action"
                    disabled={
                      !!busy || !account?.storage_available || !nodes.length
                    }
                  >
                    {busy === provider
                      ? "Connecting…"
                      : connection?.connected
                        ? "Save connection"
                        : "Connect"}
                  </button>
                </form>
                {connection?.connected && (
                  <button
                    className="btn btn-outline-primary action secondary"
                    disabled={!!busy}
                    onClick={async () => {
                      setBusy(provider);
                      try {
                        await control(
                          `account/providers/${provider}/disconnect`,
                          {},
                        );
                        setStatus(
                          `${name} disconnected. Revoke the key at ${name} if you also want to invalidate it there.`,
                        );
                        setRevision((r) => r + 1);
                      } catch (error) {
                        setStatus(
                          error instanceof Error
                            ? error.message
                            : "Disconnect failed.",
                        );
                      } finally {
                        setBusy("");
                      }
                    }}
                  >
                    Disconnect
                  </button>
                )}
              </section>
            );
          })}
        </div>
      </main>
    </ApplicationShell>
  );
}
