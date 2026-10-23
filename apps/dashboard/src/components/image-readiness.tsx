"use client";

export interface CloudImageModel {
  node_id: string;
  node_name: string;
  available: boolean;
  provider: "openai" | "gemini";
  provider_id: string;
  model: string;
  connection_id: string;
  workspace_allowed?: boolean;
  can_enable?: boolean;
}

export function imageProviderName(provider: string): string {
  return provider === "openai"
    ? "OpenAI"
    : provider === "gemini"
      ? "Google Gemini"
      : "Local images";
}

export function ImageReadiness({
  provider,
  workspace,
  models,
  selected,
  localReady,
  busy,
  allow,
  setup,
}: {
  provider: string;
  workspace: string;
  models: CloudImageModel[];
  selected?: CloudImageModel;
  localReady: boolean;
  busy: boolean;
  allow: () => void;
  setup: () => void;
}) {
  if (provider === "automatic1111") {
    return localReady ? null : (
      <div className="alert alert-warning" role="status">
        <p>
          No online computer has a permitted local image model. Choose OpenAI or
          Google Gemini above to use a cloud connection, or check your local
          worker setup.
        </p>
        <button
          type="button"
          className="btn btn-outline-primary"
          onClick={setup}
        >
          Show worker setup
        </button>
      </div>
    );
  }
  const name = imageProviderName(provider);
  const ready = models.filter((model) => model.available);
  const restricted = ready.filter((model) => model.workspace_allowed === false);
  const blocked = selected?.workspace_allowed === false ? selected : undefined;
  if (selected && !selected.available) {
    return (
      <div className="alert alert-warning" role="status">
        {selected.node_name} is offline or unavailable. Resume that computer or
        choose an online computer.
      </div>
    );
  }
  if (
    blocked ||
    (restricted.length > 0 &&
      !ready.some((model) => model.workspace_allowed !== false))
  ) {
    return (
      <div className="alert alert-warning" role="status">
        <p>
          {name} is connected.{" "}
          {blocked
            ? `${blocked.model} needs permission in ${workspace}.`
            : `${workspace} has not allowed an image model for this connection. Choose a model above.`}
        </p>
        {blocked?.can_enable && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={allow}
          >
            {busy ? "Allowing model…" : "Allow selected model in workspace"}
          </button>
        )}
        {(blocked
          ? !blocked.can_enable
          : restricted.every((model) => !model.can_enable)) && (
          <p>
            Ask a workspace owner or administrator to allow the selected image
            model.
          </p>
        )}
        {blocked?.can_enable && (
          <p className="mb-0 mt-2">
            This allows the model in this workspace. It does not generate an
            image or authorize provider charges.
          </p>
        )}
      </div>
    );
  }
  if (ready.length) return null;
  return (
    <div className="alert alert-warning" role="status">
      <p>
        {models.length
          ? `No computer offering these ${name} image models is online. Resume a permitted computer.`
          : `No accessible ${name} image model is advertised. Check the account connection, its selected computers and their cloud-image permission.`}
      </p>
      <button type="button" className="btn btn-outline-primary" onClick={setup}>
        Show worker setup
      </button>
    </div>
  );
}
