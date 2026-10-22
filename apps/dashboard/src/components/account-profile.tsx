"use client";

import { useState, type FormEvent } from "react";
import { ApplicationShell, RibbonGroup } from "./application-shell";
import { Avatar } from "./avatar";
import { control } from "../lib/control-client";

interface Profile {
  id: string;
  display_name: string;
  email: string;
  roles: string[];
  picture: string | null;
  location?: string;
}

export default function AccountProfile({
  initialUser,
}: {
  initialUser: Profile;
}) {
  const [user, setUser] = useState(initialUser);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setStatus("");
    try {
      setUser(
        await control<Profile>("account/profile", {
          display_name: form.get("display_name"),
          picture: form.get("picture") || null,
          location: form.get("location") || "",
        }),
      );
      setStatus("Profile saved.");
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Profile save not confirmed",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <ApplicationShell
      section="account"
      account={user}
      refresh={() => window.location.reload()}
      ribbon={
        <RibbonGroup label="Account">
          <a className="action secondary" href="/providers">
            AI connections
          </a>
        </RibbonGroup>
      }
    >
      <main id="main-content">
        <h1>Account settings</h1>
        <p>Your profile and personal preferences.</p>
        <form className="panel profile-form" onSubmit={(e) => void save(e)}>
          <h2>
            <Avatar name={user.display_name} picture={user.picture} /> Your
            profile
          </h2>
          <label>
            Display name
            <input
              name="display_name"
              required
              maxLength={200}
              defaultValue={user.display_name}
            />
          </label>
          <label>
            Avatar image address
            <input
              name="picture"
              type="url"
              maxLength={2048}
              placeholder="https://… (optional)"
              defaultValue={user.picture || ""}
            />
          </label>
          <p className="muted">
            Use an HTTPS image address, or leave blank for a Godfather initials
            avatar. Your browser loads the image from that host.
          </p>
          <label>
            Location (optional)
            <input
              name="location"
              maxLength={120}
              defaultValue={user.location || ""}
              placeholder="City or region you wish to share"
            />
          </label>
          <p>
            {user.email} · {user.roles.join(", ")}
          </p>
          <button className="action" disabled={busy}>
            {busy ? "Saving…" : "Save profile"}
          </button>
          <p role="status">{status}</p>
        </form>
        <section className="panel">
          <h2>AI connections</h2>
          <p>
            Manage your provider keys and the computers authorized to use them.
          </p>
          <a className="action" href="/providers">
            Manage AI connections
          </a>
        </section>
      </main>
    </ApplicationShell>
  );
}
