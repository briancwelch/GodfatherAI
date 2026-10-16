import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const credentialCookie = "godfather_local_credential";

export function localRequest(request: NextRequest, mutation = false): boolean {
  const host = request.headers.get("host") ?? "";
  if (!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host)) return false;
  if (mutation && request.headers.get("origin") !== `http://${host}`)
    return false;
  return true;
}

export function apiBase(): string {
  const value = process.env.GODFATHER_API_URL ?? "http://127.0.0.1:8000";
  const url = new URL(value);
  if (
    url.protocol !== "http:" ||
    !["127.0.0.1", "localhost", "api"].includes(url.hostname) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error("Only the local development API is supported");
  }
  return url.origin;
}

export async function backend(
  path: string,
  token: string,
  method = "GET",
  body?: string,
) {
  return fetch(`${apiBase()}/api/v1/${path}`, {
    method,
    body,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(15000),
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
}

const uuid = "[0-9a-fA-F-]{36}";
export function allowedPath(path: string, method: string): boolean {
  const reads = [
    "command-center",
    "command-center/events",
    `command-center/(jobs|nodes|agents)/${uuid}`,
    `agents/${uuid}/versions`,
    `workflow/jobs/${uuid}/artifacts/${uuid}`,
  ];
  const writes = [
    `jobs/${uuid}/(cancel|retry)`,
    `nodes/${uuid}/control`,
    `agents/${uuid}/versions/[0-9]+/control`,
    "workflow/jobs",
    "jobs",
  ];
  return (method === "GET" ? reads : method === "POST" ? writes : []).some(
    (pattern) => new RegExp(`^${pattern}$`).test(path),
  );
}

export async function proxy(request: NextRequest, segments: string[]) {
  if (!localRequest(request, request.method !== "GET"))
    return NextResponse.json(
      { detail: "Trusted local origin required" },
      { status: 403 },
    );
  const path = segments.join("/");
  if (!allowedPath(path, request.method))
    return NextResponse.json(
      { detail: "Unsupported operation" },
      { status: 404 },
    );
  const token = (await cookies()).get(credentialCookie)?.value;
  if (!token)
    return NextResponse.json(
      { detail: "Connect an administrator credential" },
      { status: 401 },
    );
  if (Number(request.headers.get("content-length") ?? 0) > 16384)
    return NextResponse.json({ detail: "Request too large" }, { status: 413 });
  try {
    const body = request.method === "POST" ? await request.text() : undefined;
    if (body && Buffer.byteLength(body) > 16384)
      return NextResponse.json(
        { detail: "Request too large" },
        { status: 413 },
      );
    const response = await backend(
      path + request.nextUrl.search,
      token,
      request.method,
      body || undefined,
    );
    const data: unknown = await response.json();
    return NextResponse.json(data, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Local API unavailable; no action confirmed" },
      { status: 503 },
    );
  }
}
