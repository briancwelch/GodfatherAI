export async function control<T>(
  path: string,
  body?: unknown,
  timeoutMs?: number,
): Promise<T> {
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
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
