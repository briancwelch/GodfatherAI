import { NextRequest, NextResponse } from "next/server";
import { backend, credentialCookie, localRequest } from "@/lib/control-server";

export const runtime = "nodejs";
export async function POST(request: NextRequest) {
  if (!localRequest(request, true))
    return NextResponse.json(
      { detail: "Trusted local origin required" },
      { status: 403 },
    );
  try {
    if (Number(request.headers.get("content-length") ?? 0) > 256)
      return NextResponse.json(
        { detail: "Invalid credential" },
        { status: 422 },
      );
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 256)
      return NextResponse.json(
        { detail: "Invalid credential" },
        { status: 422 },
      );
    const { token } = JSON.parse(raw) as { token?: unknown };
    if (typeof token !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(token))
      return NextResponse.json(
        { detail: "Invalid credential" },
        { status: 422 },
      );
    const response = await backend("command-center", token);
    if (!response.ok)
      return NextResponse.json(
        {
          detail:
            response.status === 401 || response.status === 403
              ? "Administrator credential rejected"
              : "Local API unavailable",
        },
        { status: response.status },
      );
    const result = NextResponse.json(
      { connected: true },
      { headers: { "Cache-Control": "no-store" } },
    );
    result.cookies.set(credentialCookie, token, {
      httpOnly: true,
      sameSite: "strict",
      secure: false,
      path: "/",
      maxAge: 8 * 60 * 60,
    });
    return result;
  } catch {
    return NextResponse.json(
      { detail: "Could not connect to the local API" },
      { status: 503 },
    );
  }
}

export async function DELETE(request: NextRequest) {
  if (!localRequest(request, true))
    return NextResponse.json(
      { detail: "Trusted local origin required" },
      { status: 403 },
    );
  const result = NextResponse.json({ connected: false });
  result.cookies.set(credentialCookie, "", {
    httpOnly: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return result;
}
