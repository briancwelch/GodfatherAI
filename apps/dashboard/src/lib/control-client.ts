export async function control<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/control/${path}`, {
    method: body === undefined ? "GET" : "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : response.status === 422
          ? "Configuration rejected. Check the workflow, requirements and field limits."
          : `Operation not confirmed (${response.status}). Check your session and permissions.`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
