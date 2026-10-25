"use client";

import { useFeedback } from "./toast-notifications";

import { useState } from "react";
import { control } from "../lib/control-client";
import type { ModelInfo, Snapshot } from "../lib/contracts";

export function ObservedInference({
  model,
  metrics,
}: {
  model: ModelInfo;
  metrics: Snapshot["metrics"];
}) {
  const deployment = model.deployment;
  const measurement = (
    metrics?.recent_measurements ??
    metrics?.recent_attempts ??
    []
  ).find(
    (sample) =>
      sample.node_id === model.node_id &&
      sample.usage &&
      sample.deployment?.provider === deployment.provider &&
      sample.deployment.provider_id === deployment.provider_id &&
      sample.deployment.identifier === deployment.identifier &&
      (sample.deployment.connection_id ?? null) ===
        (deployment.connection_id ?? null) &&
      (sample.deployment.shared_inference_group_id ?? null) ===
        (deployment.shared_inference_group_id ?? null) &&
      (sample.deployment.digest ?? null) === (deployment.digest ?? null),
  );
  const usage = measurement?.usage;
  if (!usage) return <>No recent measurement</>;
  return (
    <>
      <span
        title={
          "source" in measurement
            ? measurement.source === "workflow_step"
              ? "Committed workflow model step"
              : "Completed inference attempt"
            : "Completed inference attempt"
        }
      >
        {usage.duration_seconds == null
          ? "Unknown duration"
          : `${usage.duration_seconds.toFixed(2)}s`}
      </span>
      <small>
        {usage.input_tokens ?? "Unknown"} input /{" "}
        {usage.output_tokens ?? "Unknown"} output tokens
      </small>
      <small>
        {usage.tokens_per_second?.toFixed(1) ?? "Unknown"} tokens/s
        {usage.rate_source === "worker_estimate"
          ? " (estimated)"
          : usage.rate_source === "provider_reported"
            ? " (provider)"
            : ""}
      </small>
      {usage.first_token_seconds != null && (
        <small>First token {usage.first_token_seconds.toFixed(2)}s</small>
      )}
    </>
  );
}

export function modelAgentUrl(workspace: string, model: ModelInfo) {
  const d = model.deployment;
  if (d.operations?.includes("image_generation")) return "/images";
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
  useFeedback(error);
  const restricted = model.workspace_allowed === false;
  if (!restricted)
    return (
      <a
        className="btn btn-primary action"
        href={modelAgentUrl(workspace, model)}
      >
        {model.deployment.operations?.includes("image_generation")
          ? "Generate images"
          : "Use model / create agent"}
      </a>
    );
  return (
    <div>
      <button
        type="button"
        className="btn btn-primary action"
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
        {busy
          ? "Enabling model…"
          : model.deployment.operations?.includes("image_generation")
            ? "Allow in workspace / generate images"
            : "Allow in workspace / create agent"}
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
