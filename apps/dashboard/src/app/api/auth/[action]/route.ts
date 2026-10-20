import { NextRequest, NextResponse } from "next/server";
import {
  apiBase,
  credentialCookie,
  localRequest,
  webOrigin,
} from "@/lib/control-server";

export const runtime = "nodejs";

async function handle(request: NextRequest, action: string) {
  const mutation = request.method === "POST";
  if (!localRequest(request, mutation))
    return NextResponse.json(
      { detail: "Trusted application origin required" },
      { status: 403 },
    );
  if (
    !(mutation ? ["start", "logout", "revoke"] : ["callback", "me"]).includes(
      action,
    )
  )
    return NextResponse.json(
      { detail: "Unsupported authentication operation" },
      { status: 404 },
    );
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Origin: webOrigin(),
  };
  const session = request.cookies.get(credentialCookie)?.value;
  if (session) headers["X-Godfather-Session"] = session;
  const browser = request.cookies.get("godfather_login")?.value;
  if (browser && /^[A-Za-z0-9_-]{43}$/.test(browser))
    headers.Cookie = `godfather_login=${browser}`;
  try {
    let body: string | undefined;
    let workerChallenge: string | undefined;
    if (action === "start") {
      if (Number(request.headers.get("content-length") ?? 0) > 2048)
        return NextResponse.json(
          { detail: "Request too large" },
          { status: 413 },
        );
      const raw = await request.text();
      if (Buffer.byteLength(raw) > 2048)
        return NextResponse.json(
          { detail: "Request too large" },
          { status: 413 },
        );
      const form = new URLSearchParams(raw);
      const challenge = form.get("worker_challenge") ?? "";
      if (/^[a-f0-9]{64}$/.test(challenge)) workerChallenge = challenge;
      body = JSON.stringify({ invitation: form.get("invitation") || null });
    } else if (mutation) body = "{}";
    const path = action === "revoke" ? "sessions/revoke" : action;
    const upstream = await fetch(
      `${apiBase()}/api/v1/auth/${path}${action === "callback" ? request.nextUrl.search : ""}`,
      {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(30000),
      },
    );
    const outgoing = new Headers({
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
    });
    if (action === "start") {
      outgoing.append(
        "Set-Cookie",
        `godfather_worker_return=${workerChallenge ?? ""}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${workerChallenge ? 600 : 0}${webOrigin().startsWith("https:") ? "; Secure" : ""}`,
      );
    }
    for (const value of upstream.headers.getSetCookie())
      outgoing.append("Set-Cookie", value);
    const location = upstream.headers.get("location");
    if (location) {
      const url = new URL(location);
      if (
        url.origin !== webOrigin() &&
        !(action === "start" && url.origin === "https://accounts.google.com")
      )
        throw new Error("Untrusted authentication redirect");
      const workerReturn =
        request.cookies.get("godfather_worker_return")?.value ?? "";
      const returnToWorker =
        action === "callback" &&
        url.origin === webOrigin() &&
        url.pathname === "/" &&
        !url.search &&
        /^[a-f0-9]{64}$/.test(workerReturn);
      outgoing.set(
        "Location",
        returnToWorker
          ? `${webOrigin()}/worker-enrollment#challenge=${workerReturn}`
          : location,
      );
      if (action === "callback")
        outgoing.append(
          "Set-Cookie",
          "godfather_worker_return=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
        );
      if (
        action === "start" &&
        request.headers.get("accept")?.includes("application/json")
      ) {
        outgoing.delete("Location");
        return NextResponse.json(
          { authorization_url: location },
          { headers: outgoing },
        );
      }
      return new Response(null, { status: 303, headers: outgoing });
    }
    if (action === "start") {
      if (request.headers.get("accept")?.includes("application/json"))
        return NextResponse.json(
          { detail: "Google Sign-In unavailable or not configured" },
          { status: upstream.status, headers: outgoing },
        );
      outgoing.set("Location", `${webOrigin()}/?auth=unavailable`);
      return new Response(null, { status: 303, headers: outgoing });
    }
    return NextResponse.json(await upstream.json(), {
      status: upstream.status,
      headers: outgoing,
    });
  } catch {
    if (action === "start" || action === "callback")
      return NextResponse.redirect(`${webOrigin()}/?auth=unavailable`, 303);
    return NextResponse.json(
      { detail: "Authentication service unavailable" },
      { status: 503 },
    );
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ action: string }> },
) {
  return handle(request, (await context.params).action);
}
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ action: string }> },
) {
  return handle(request, (await context.params).action);
}
