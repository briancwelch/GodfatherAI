"use client";

import { useEffect, useState } from "react";

interface Download {
  platform: string;
  filename: string;
  sha256: string;
  signing: string;
}

export function ConnectComputer() {
  const [address, setAddress] = useState("");
  const [downloads, setDownloads] = useState<Download[]>([]);
  const [status, setStatus] = useState("Checking worker downloads…");
  useEffect(() => {
    fetch("/downloads/manifest.json", {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const data: { artifacts?: Download[] } = await response.json();
        const items = data.artifacts ?? [];
        if (
          !Array.isArray(items) ||
          !items.every(
            (item) =>
              typeof item.signing === "string" &&
              /^[a-f0-9]{64}$/.test(item.sha256) &&
              /^godfather-worker-[a-z0-9.-]+-(?:windows-x64-setup\.exe|macos-(?:arm64|x64)-installer\.dmg)$/.test(
                item.filename,
              ),
          )
        )
          throw new Error();
        setDownloads(items);
        setStatus(
          items.length
            ? ""
            : "Worker downloads have not been published by your administrator yet.",
        );
      })
      .catch(() =>
        setStatus(
          "Worker downloads are unavailable. Ask your administrator for the installer.",
        ),
      )
      .finally(() => setAddress(window.location.origin));
  }, []);
  return (
    <section className="panel">
      <h2>Connect a computer</h2>
      <ol>
        <li>
          Install The Godfather Worker on the computer you want to contribute.
        </li>
        <li>Open it, enter this Command Center address and click Connect.</li>
        <li>
          Sign in with your invited Google account and approve the matching
          code. Your worker connects automatically.
        </li>
      </ol>
      <label>
        Command Center address
        <input readOnly value={address} />
      </label>
      <button
        className="action"
        disabled={!address}
        onClick={() => {
          void navigator.clipboard
            .writeText(address)
            .then(() => setStatus("Address copied."))
            .catch(() => setStatus("Select and copy the address above."));
        }}
      >
        Copy address
      </button>
      {status && <p role="status">{status}</p>}
      {downloads.map((item) => (
        <div key={item.filename}>
          <a className="action" href={`/downloads/${item.filename}`} download>
            Download for {item.platform}
          </a>
          <p>{item.signing}</p>
          <details>
            <summary>Verify download</summary>
            <code>SHA-256: {item.sha256}</code>
          </details>
        </div>
      ))}
      <p>
        HTTPS connects from anywhere. Tailscale is optional. Your computer keeps
        control of its files, tools and paid AI credentials.
      </p>
    </section>
  );
}
