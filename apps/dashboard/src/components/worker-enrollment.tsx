"use client";

import { useEffect, useState, type FormEvent } from "react";
import { GoogleLogin } from "@/components/google-login";

export default function WorkerEnrollment() {
  const [challenge, setChallenge] = useState("");
  const [owner, setOwner] = useState<string | null>(null);
  const [status, setStatus] = useState("Checking sign-in…");
  const [busy, setBusy] = useState(false);
  const [approved, setApproved] = useState(false);
  const [nodeName, setNodeName] = useState("");
  useEffect(() => {
    const value =
      new URLSearchParams(location.hash.slice(1)).get("challenge") ?? "";
    fetch("/api/control/auth/me")
      .then(async (r) => {
        if (/^[a-f0-9]{64}$/.test(value)) setChallenge(value);
        if (!r.ok) {
          setStatus(
            "Sign in with your invited Google account to approve this computer.",
          );
          return;
        }
        const user = await r.json();
        if (!user.permissions.includes("nodes.contribute")) {
          setStatus(
            "Your account cannot register nodes. Contact an administrator.",
          );
          return;
        }
        setOwner(user.email);
        setStatus("");
      })
      .catch(() => setStatus("Command Center unavailable. Try again shortly."));
  }, []);
  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "");
    setBusy(true);
    try {
      const response = await fetch(
        "/api/control/administration/worker-enrollments",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ challenge, name }),
        },
      );
      if (!response.ok)
        throw new Error(
          "Approval refused. Reconnect from the app, or contact your administrator.",
        );
      setApproved(true);
      setNodeName(name);
      setStatus(
        "Approved. Your worker will connect automatically. You can close this page and return to the app.",
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Approval failed.");
    } finally {
      setBusy(false);
    }
  }
  async function revoke() {
    setBusy(true);
    try {
      const response = await fetch(
        "/api/control/administration/worker-enrollments/revoke",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ challenge, name: nodeName }),
        },
      );
      if (!response.ok) throw new Error("Cancellation not confirmed.");
      setStatus(
        "Pairing cancelled. If you already finished connecting, revoke the machine credential in Administration → Owned node onboarding as well.",
      );
    } catch {
      setStatus(
        "Cancellation not confirmed. Check your session and try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="panel connect-panel">
      <h1>Connect your computer</h1>
      <p>
        Only approve a connection you started in The Godfather Worker on your
        own computer.
      </p>
      {status && <p role="status">{status}</p>}
      {approved && (
        <button className="action" disabled={busy} onClick={revoke}>
          Cancel pairing approval
        </button>
      )}
      {!owner && <GoogleLogin workerChallenge={challenge} />}
      {owner && !challenge && (
        <p role="alert">
          Open this page using Connect to The Godfather in the worker app.
        </p>
      )}
      {owner && challenge && !approved && (
        <form onSubmit={approve}>
          <p>Signed in as {owner}</p>
          <p>
            Compare this code with the code in your worker:{" "}
            <strong>{challenge.slice(0, 12).toUpperCase()}</strong>
          </p>
          <label>
            Node display name
            <input
              name="name"
              required
              maxLength={100}
              defaultValue="My computer"
            />
          </label>
          <p>
            Registration grants no shell, private files, repositories, paid
            inference, or shared workloads. Choose resource contributions
            locally afterward.
          </p>
          <label>
            <input type="checkbox" required />
            The code matches my computer, and I approve its registration.
          </label>
          <button className="action" disabled={busy}>
            {busy ? "Approving…" : "Approve this computer"}
          </button>
        </form>
      )}
    </main>
  );
}
