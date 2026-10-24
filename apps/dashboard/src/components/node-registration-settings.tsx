"use client";

import { useEffect, useState, type FormEvent } from "react";
import { control } from "../lib/control-client";

type Policy = {
  members_can_add_nodes: boolean;
  contributors_can_add_nodes: boolean;
};

export function NodeRegistrationSettings() {
  const [draft, setDraft] = useState<Policy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    control<Policy>("administration/node-registration")
      .then((policy) => {
        if (active) setDraft(policy);
      })
      .catch((e) => {
        if (active)
          setError(e instanceof Error ? e.message : "Permissions unavailable.");
      });
    return () => {
      active = false;
    };
  }, []);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setDraft(
        await control<Policy>("administration/node-registration", draft),
      );
      setMessage("Node registration permissions saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save not confirmed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card panel" aria-label="Node registration permissions">
      <h2>Who can add nodes</h2>
      <p>
        Platform administrators can always add their own computers. Turn off
        both switches to allow only administrators to add nodes. Accounts with
        several roles may add nodes if any assigned role allows it.
      </p>
      <p>
        Existing computers keep connecting and contributing. Owners can
        reconnect an existing node to retain its name and job history. Node
        ownership, workspace access and local host permissions remain in force.
      </p>
      {error && (
        <p role="alert" className="alert alert-danger">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="alert alert-success">
          {message}
        </p>
      )}
      {!draft ? (
        <p role="status">
          {error
            ? "Refresh to retry loading permissions."
            : "Loading saved permissions…"}
        </p>
      ) : (
        <form onSubmit={save} aria-busy={busy}>
          <fieldset disabled={busy}>
            <legend>New node registration</legend>
            {(
              [
                ["members_can_add_nodes", "Members can add nodes"],
                ["contributors_can_add_nodes", "Contributors can add nodes"],
              ] as const
            ).map(([key, label]) => (
              <div className="form-check form-switch" key={key}>
                <input
                  className="form-check-input"
                  role="switch"
                  type="checkbox"
                  id={key}
                  checked={draft[key]}
                  onChange={(event) => {
                    setDraft({ ...draft, [key]: event.target.checked });
                    setMessage("");
                  }}
                />
                <label className="form-check-label" htmlFor={key}>
                  {label}
                </label>
              </div>
            ))}
            <button className="btn btn-primary action" type="submit">
              {busy ? "Saving…" : "Save node permissions"}
            </button>
          </fieldset>
        </form>
      )}
    </section>
  );
}
