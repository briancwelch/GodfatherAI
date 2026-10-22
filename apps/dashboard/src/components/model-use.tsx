"use client";

import { useState } from "react";
import { control } from "../lib/control-client";
import type { ModelInfo } from "../lib/contracts";

export function modelAgentUrl(workspace: string, model: ModelInfo) {
  const d = model.deployment;
  const choice = `${d.provider}:${d.identifier}${d.connection_id ? `:${d.connection_id}` : ""}`;
  return `/agents?workspace=${workspace}&model=${encodeURIComponent(choice)}`;
}

export function UseModel({
  workspace,
  model,
}: {
  workspace: string;
  model: ModelInfo;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const restricted = model.workspace_allowed === false;
  if (!restricted)
    return (
      <a className="action" href={modelAgentUrl(workspace, model)}>
        Use model / create agent
      </a>
    );
  return (
    <div>
      <button
        type="button"
        className="action"
        disabled={busy || !model.can_enable}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await control("models/workspace-access", {
              workspace_id: workspace,
              node_id: model.node_id,
              provider_id: model.deployment.provider_id,
              identifier: model.deployment.identifier,
            });
            window.location.assign(modelAgentUrl(workspace, model));
          } catch (e) {
            setError(
              e instanceof Error
                ? e.message
                : "Workspace model access was not saved",
            );
            setBusy(false);
          }
        }}
      >
        {busy ? "Enabling model…" : "Allow in workspace / create agent"}
      </button>
      {!model.can_enable && (
        <p>Ask a workspace administrator to allow this model.</p>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

export function ModelAvailability({ model }: { model: ModelInfo }) {
  return (
    <span>
      {model.deployment.provider === "ollama"
        ? "Installed locally"
        : `Connected ${model.deployment.provider === "openai" ? "OpenAI" : model.deployment.provider === "anthropic" ? "Anthropic" : model.deployment.provider} API`}
      {model.workspace_allowed === false
        ? " · workspace access required"
        : " · allowed in workspace"}
      {(model.worker_available ?? model.available)
        ? " · worker online"
        : " · worker offline or unavailable"}
    </span>
  );
}
