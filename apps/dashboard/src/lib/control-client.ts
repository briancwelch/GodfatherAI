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

export async function control<T>(
  path: string,
  body?: unknown,
  timeoutMs?: number,
): Promise<T> {
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
      signal: timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined,
    });
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
