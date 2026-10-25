import {
  dismissToast,
  notifyError,
  notifyToast,
  watchJob,
} from "./notifications";

export class ControlError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

let signInRequired = false;
let sessionGeneration = 0;
let sessionOwner = "";
const sessionListeners = new Set<() => void>();
let verification: {
  controller: AbortController;
  promise: Promise<unknown>;
} | null = null;

export const authenticationRequired = () => signInRequired;
export function subscribeAuthentication(listener: () => void) {
  sessionListeners.add(listener);
  return () => {
    sessionListeners.delete(listener);
  };
}
export function rememberSessionOwner(owner: string) {
  if (!sessionOwner) sessionOwner = owner;
}
function requireAuthentication() {
  if (signInRequired) return;
  signInRequired = true;
  sessionGeneration += 1;
  sessionListeners.forEach((listener) => listener());
}
export function cancelSessionVerification() {
  verification?.controller.abort();
  verification = null;
}
export function verifySession<T>(): Promise<T> {
  if (verification) return verification.promise as Promise<T>;
  const generation = sessionGeneration;
  const controller = new AbortController();
  const promise = control<{ id: string }>(
    "auth/me",
    undefined,
    10000,
    controller.signal,
  )
    .then((account) => {
      if (controller.signal.aborted || generation !== sessionGeneration)
        throw new ControlError("Sign in required", 401);
      if (typeof account.id !== "string" || !account.id)
        throw new ControlError("Session verification unavailable", 503);
      if (sessionOwner && sessionOwner !== account.id) {
        // A different account must never inherit the previous account's cached UI.
        requireAuthentication();
        window.location.reload();
        throw new ControlError(
          "Account changed. Reloading the application.",
          401,
        );
      }
      sessionOwner = account.id;
      if (signInRequired) {
        signInRequired = false;
        sessionListeners.forEach((listener) => listener());
      }
      return account;
    })
    .finally(() => {
      if (verification?.controller === controller) verification = null;
    });
  verification = { controller, promise };
  return promise as Promise<T>;
}

export async function control<T>(
  path: string,
  body?: unknown,
  timeoutMs?: number,
  signal?: AbortSignal,
): Promise<T> {
  signal?.throwIfAborted();
  if (signInRequired && path !== "auth/me")
    throw new ControlError("Sign in required", 401);
  const operation =
    body === undefined ? "" : `operation:${crypto.randomUUID()}`;
  if (operation)
    notifyToast({
      id: operation,
      kind: "processing",
      title: "Processing request",
      message: "Waiting for coordinator confirmation",
    });
  try {
    const response = await fetch(`/api/control/${path}`, {
      method: body === undefined ? "GET" : "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: timeoutMs
        ? signal
          ? AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)])
          : AbortSignal.timeout(timeoutMs)
        : signal,
    });
    signal?.throwIfAborted();
    if (response.status === 401) {
      requireAuthentication();
      throw new ControlError("Sign in required", 401);
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const fields = Array.isArray(payload?.detail)
        ? payload.detail
            .slice(0, 8)
            .flatMap((issue: { loc?: unknown; msg?: unknown }) => {
              if (
                !issue ||
                typeof issue.msg !== "string" ||
                !Array.isArray(issue.loc)
              )
                return [];
              const location = issue.loc
                .filter(
                  (part) =>
                    part !== "body" &&
                    (typeof part === "string" || typeof part === "number"),
                )
                .join(" > ");
              return [`${location || "Request"}: ${issue.msg}`];
            })
        : [];
      const detail =
        typeof payload?.detail === "string"
          ? payload.detail
          : fields.length
            ? `Check these fields: ${fields.join("; ")}`
            : response.status === 422
              ? "Configuration rejected. Check the workflow, requirements and field limits."
              : `Operation not confirmed (${response.status}). Check your session and permissions.`;
      throw new ControlError(detail, response.status);
    }
    const result = await response.json();
    signal?.throwIfAborted();
    if (operation) {
      dismissToast(operation);
      const isTasks =
        path === "distributed/tasks" || path === "distributed/jobs";
      const isJob =
        isTasks ||
        [
          "jobs",
          "workflow/jobs",
          "workloads/jobs",
          "shared-inference/jobs",
          "models/install",
        ].includes(path);
      if (isJob && typeof result.id === "string") {
        watchJob({
          id: result.id,
          path: isTasks
            ? `distributed/tasks/${result.id}`
            : `command-center/jobs/${result.id}`,
          href: isTasks
            ? `/distributed-tasks?workspace=${result.workspace_id}&job=${result.id}`
            : `/jobs/${result.id}`,
          name: isTasks ? result.name || "Distributed tasks" : "Job",
        });
      } else
        notifyToast({
          id: operation,
          kind: "success",
          title: "Request confirmed",
          message: "The coordinator confirmed the change.",
        });
    }
    return result as T;
  } catch (error) {
    if (operation) dismissToast(operation);
    if (
      !signal?.aborted &&
      !(error instanceof ControlError && error.status === 401)
    )
      notifyError(
        error instanceof Error && error.name === "TimeoutError"
          ? "Confirmation timed out. Check job history before retrying."
          : error instanceof TypeError
            ? "The coordinator could not be reached. Check job history before retrying."
            : error instanceof Error
              ? error.message
              : "Operation not confirmed",
      );
    throw error;
  }
}
