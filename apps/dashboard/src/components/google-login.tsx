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
        Use your invited Google account. A Google account alone does not grant
        platform access.
      </p>
      {error && (
        <p role="alert">
          {error === "unavailable"
            ? "Google Sign-In is unavailable or not configured."
            : error === "denied"
              ? "Sign-in was not authorized. Check your invitation or contact an administrator."
              : "Sign in again. Your session may have expired or been revoked."}
        </p>
      )}
      {failure && <p role="alert">{failure}</p>}
      <form onSubmit={start} action="/api/auth/start" method="post">
        <label>
          Invitation token (first sign-in only)
          <input
            name="invitation"
            type="password"
            autoComplete="off"
            maxLength={43}
          />
        </label>
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
