import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { redirect } from "next/navigation";

export const credentialCookie = "godfather_session";

export function webOrigin(): string {
  const value = process.env.GODFATHER_WEB_ORIGIN ?? "http://127.0.0.1:3000";
  const url = new URL(value);
  if (
    url.protocol !== "https:" &&
    !(
      url.protocol === "http:" &&
      ["127.0.0.1", "localhost"].includes(url.hostname)
    )
  )
    throw new Error("Unsupported application origin");
  if (url.origin !== value)
    throw new Error("An exact application origin is required");
  return value;
}

export function localRequest(request: NextRequest, mutation = false): boolean {
  const host = request.headers.get("host") ?? "";
  if (host !== new URL(webOrigin()).host) return false;
  if (mutation && request.headers.get("origin") !== webOrigin()) return false;
  return true;
}

export function apiBase(): string {
  const value = process.env.GODFATHER_API_URL ?? "http://127.0.0.1:8000";
  const url = new URL(value);
  if (
    !(
      (url.protocol === "http:" &&
        ["127.0.0.1", "localhost", "api"].includes(url.hostname)) ||
      url.protocol === "https:"
    ) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error(
      "Configure an exact HTTPS API origin or an allowed internal API origin",
    );
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
    signal: AbortSignal.timeout(
      path === "administration/workspace-archive" ? 60000 : 15000,
    ),
    headers: {
      "X-Godfather-Session": token,
      Origin: webOrigin(),
      "Content-Type": "application/json",
    },
  });
}

const uuid = "[0-9a-fA-F-]{36}";
export function allowedPath(path: string, method: string): boolean {
  const reads = [
    "workloads/options",
    `workloads/jobs/${uuid}/files/${uuid}/[0-9]+`,
    "account/providers",
    "agent-options",
    "coding/repositories",
    "tools",
    "models/install-options",
    "provider-connections",
    `provider-connections/${uuid}/(usage|grants)`,
    "auth/me",
    "administration/(users|invitations|audit|node-credentials)",
    `administration/workspaces/${uuid}/members`,
    `administration/workspaces/${uuid}/members/${uuid}`,
    "command-center",
    "command-center/events",
    `command-center/jobs/${uuid}/checkpoints`,
    `command-center/(jobs|nodes|agents)/${uuid}`,
    `agents/${uuid}/versions`,
    `workflow/jobs/${uuid}/artifacts/${uuid}`,
  ];
  const writes = [
    "workloads/jobs",
    "account/providers/(openai|anthropic)(/(disconnect|computers))?",
    "models/install",
    "provider-connections",
    `provider-connections/${uuid}/(policy|control|test|grants)`,
    `provider-connections/${uuid}/grants/${uuid}/revoke`,
    "administration/bulk-delete",
    "administration/workspace-archive",
    "administration/worker-enrollments",
    "administration/worker-enrollments/revoke",
    "agents",
    `agents/${uuid}/versions`,
    "administration/(invitations|workspaces|node-credentials)",
    `administration/node-credentials/${uuid}/revoke`,
    `administration/users/${uuid}(/revoke-sessions)?`,
    `administration/invitations/${uuid}/revoke`,
    `administration/workspaces/${uuid}/(members|policy)`,
    `jobs/${uuid}/(cancel|retry)`,
    `jobs/${uuid}/result-actions`,
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
      { detail: "Google Sign-In required" },
      { status: 401 },
    );
  const bodyLimit = path === "workloads/jobs" ? 1500000 : 16384;
  if (Number(request.headers.get("content-length") ?? 0) > bodyLimit)
    return NextResponse.json({ detail: "Request too large" }, { status: 413 });
  try {
    const body = request.method === "POST" ? await request.text() : undefined;
    if (body && Buffer.byteLength(body) > bodyLimit)
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
    if (response.ok && path === "administration/workspace-archive") {
      return new NextResponse(response.body, {
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition":
            response.headers.get("content-disposition") ||
            'attachment; filename="godfather-workspaces.zip"',
          ...(response.headers.get("content-length")
            ? { "Content-Length": response.headers.get("content-length")! }
            : {}),
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
    if (
      response.ok &&
      request.method === "GET" &&
      new RegExp(`^workloads/jobs/${uuid}/files/${uuid}/[0-9]+$`).test(path)
    ) {
      return new NextResponse(await response.arrayBuffer(), {
        headers: {
          "Content-Type":
            response.headers.get("content-type") || "application/octet-stream",
          "Content-Disposition":
            response.headers.get("content-disposition") || "attachment",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          "Content-Security-Policy": "default-src 'none'; sandbox",
        },
      });
    }
    if (
      response.ok &&
      request.method === "GET" &&
      request.nextUrl.searchParams.get("download") === "1" &&
      new RegExp(`^workflow/jobs/${uuid}/artifacts/${uuid}$`).test(path)
    ) {
      return new NextResponse(await response.text(), {
        headers: {
          "Cache-Control": "no-store",
          "Content-Type": "application/json",
          "Content-Disposition": `attachment; filename="artifact-${segments.at(-1)}.json"`,
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
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

export async function requireUser() {
  const token = (await cookies()).get(credentialCookie)?.value;
  if (!token) redirect("/?auth=required");
  let response: Response;
  try {
    response = await backend("auth/me", token);
  } catch {
    redirect("/?auth=unavailable");
  }
  if (!response.ok) redirect("/?auth=required");
  return response.json();
}
