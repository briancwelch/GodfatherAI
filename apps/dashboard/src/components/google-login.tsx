"use client";

import { useState, type FormEvent } from "react";

export function GoogleLogin({
  error,
  workerChallenge,
}: {
  error?: string;
  workerChallenge?: string;
}) {
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFailure("");
    setBusy(true);
    try {
      const response = await fetch("/api/auth/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
        body: new URLSearchParams({
          invitation: String(form.get("invitation") ?? ""),
          worker_challenge: workerChallenge ?? "",
        }),
      });
      if (!response.ok)
        throw new Error("Google Sign-In is unavailable or not configured.");
      const data: { authorization_url: string } = await response.json();
      window.location.assign(data.authorization_url);
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "Sign-in unavailable.");
      setBusy(false);
    }
  }
  return (
    <section className="panel connect-panel">
      <h2>Sign in to The Godfather</h2>
      <p>
        Continue with the exact Google account email your administrator invited.
        No invitation code is needed. Your administrator must invite this
        account. Tailscale is optional.
      </p>
      {error && (
        <p role="alert">
          {error === "unavailable"
            ? "Google Sign-In is unavailable or not configured."
            : error === "denied"
              ? "Sign-in was not authorized. Choose the exact invited Google email. Ask your administrator to check that one invitation is active and unexpired."
              : "Sign in again. Your session may have expired or been revoked."}
        </p>
      )}
      {failure && <p role="alert">{failure}</p>}
      <form onSubmit={start} action="/api/auth/start" method="post">
        <details>
          <summary>Have an invitation code?</summary>
          <label>
            Invitation token (optional)
            <input
              name="invitation"
              type="password"
              autoComplete="off"
              maxLength={43}
            />
          </label>
        </details>
        <button className="action" type="submit" disabled={busy}>
          {busy ? "Connecting…" : "Continue with Google"}
        </button>
      </form>
      <p className="muted">
        Basic identity access only. Your Google tokens are never stored in
        browser storage.
      </p>
    </section>
  );
}
