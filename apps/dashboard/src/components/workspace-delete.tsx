"use client";

import { ProgressBar } from "./progress-bar";

import { useFeedback } from "./toast-notifications";

import { useId, useRef, useState } from "react";
import { CommandIcon } from "./command-icon";

export function WorkspaceDelete({
  ids,
  names,
  disabled,
  onDelete,
}: {
  ids: string[];
  names: string[];
  disabled: boolean;
  onDelete: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const abort = useRef<AbortController | null>(null);
  const heading = useId();
  const description = useId();
  const [phase, setPhase] = useState<
    "idle" | "preparing" | "downloading" | "ready" | "deleting"
  >("idle");
  const [progress, setProgress] = useState<{
    received: number;
    total: number | null;
  }>({ received: 0, total: null });
  const [downloaded, setDownloaded] = useState(false);
  const [skip, setSkip] = useState(false);
  const [error, setError] = useState("");
  useFeedback(error);
  const exporting = phase === "preparing" || phase === "downloading";
  const deleting = phase === "deleting";
  function close() {
    abort.current?.abort();
    abort.current = null;
    dialog.current?.close();
  }
  async function archive() {
    const controller = new AbortController();
    abort.current = controller;
    setError("");
    setPhase("preparing");
    setDownloaded(false);
    setProgress({ received: 0, total: null });
    try {
      const response = await fetch(
        "/api/control/administration/workspace-archive",
        {
          method: "POST",
          cache: "no-store",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids }),
          signal: controller.signal,
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          typeof payload?.detail === "string"
            ? payload.detail
            : "Archive could not be prepared. Nothing was deleted.",
        );
      }
      if (
        !response.body ||
        !response.headers.get("content-type")?.includes("application/zip")
      )
        throw new Error(
          "The archive response was incomplete. Nothing was deleted.",
        );
      const total = Number(response.headers.get("content-length")) || null;
      setPhase("downloading");
      const reader = response.body.getReader();
      const chunks: BlobPart[] = [];
      let received = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.byteLength;
        setProgress({ received, total });
      }
      if (!received || (total !== null && received !== total))
        throw new Error(
          "The archive download was interrupted. Nothing was deleted.",
        );
      if (controller.signal.aborted) return;
      const blob = new Blob(chunks, { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download =
        /filename="([a-zA-Z0-9._-]+)"/.exec(
          response.headers.get("content-disposition") || "",
        )?.[1] || "godfather-workspaces.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      setDownloaded(true);
      setSkip(false);
      setPhase("ready");
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(
          e instanceof Error
            ? e.message
            : "Archive failed. Nothing was deleted.",
        );
        setPhase("idle");
      }
    } finally {
      if (abort.current === controller) abort.current = null;
    }
  }
  return (
    <>
      <button
        type="button"
        className="btn btn-outline-primary action secondary"
        disabled={disabled}
        onClick={() => {
          setPhase("idle");
          setDownloaded(false);
          setSkip(false);
          setError("");
          setProgress({ received: 0, total: null });
          dialog.current?.showModal();
        }}
      >
        Delete selected
      </button>
      <dialog
        ref={dialog}
        className="workspace-delete-dialog"
        aria-labelledby={heading}
        aria-describedby={description}
        onCancel={(e) => {
          if (deleting) e.preventDefault();
          else abort.current?.abort();
        }}
        onClose={() => abort.current?.abort()}
      >
        <div className="archive-dialog-heading">
          <span className="archive-dialog-icon">
            <CommandIcon label="Downloads" />
          </span>
          <div>
            <p className="eyebrow">WORKSPACE ARCHIVE</p>
            <h2 id={heading}>Keep a copy before you go</h2>
          </div>
        </div>
        <p id={description}>
          Download your workspace data before deleting{" "}
          {ids.length === 1
            ? "this workspace"
            : `these ${ids.length} workspaces`}
          . Your archive stays with you.
        </p>
        <ul className="archive-workspace-names">
          {names.map((name, i) => (
            <li key={ids[i]}>
              <CommandIcon label="Workspaces" />
              {name}
            </li>
          ))}
        </ul>
        <ol className="archive-steps" aria-label="Archive steps">
          <li data-active={exporting}>
            <span>1</span>
            <div>
              <strong>Prepare archive</strong>
              <small>Gather records and verify artifacts</small>
            </div>
          </li>
          <li data-active={phase === "downloading" || downloaded}>
            <span>2</span>
            <div>
              <strong>Download ZIP</strong>
              <small>
                {downloaded
                  ? "Archive received - check your downloads"
                  : "A portable copy for safekeeping"}
              </small>
            </div>
          </li>
          <li data-active={deleting}>
            <span>3</span>
            <div>
              <strong>Confirm deletion</strong>
              <small>You decide when to continue</small>
            </div>
          </li>
        </ol>
        <p className="archive-includes">
          Includes workspace settings, memberships, agents, jobs, workflow
          history, checkpoints and verified artifacts. Account secrets, private
          billing records and worker-local files stay outside the archive.
          Automatic restore is not available.
        </p>
        {exporting && (
          <div className="archive-progress" role="status" aria-live="polite">
            <div>
              <strong>
                {phase === "preparing"
                  ? "Preparing your archive..."
                  : "Downloading your archive..."}
              </strong>
              <span>
                {phase === "downloading"
                  ? `${(progress.received / 1024 / 1024).toFixed(1)} MiB${progress.total ? ` / ${(progress.total / 1024 / 1024).toFixed(1)} MiB` : " received"}`
                  : "Verifying workspace data"}
              </span>
            </div>
            <ProgressBar
              aria-label="Workspace archive progress"
              max={100}
              value={
                phase === "downloading" && progress.total
                  ? Math.min(100, (progress.received / progress.total) * 100)
                  : undefined
              }
            />
          </div>
        )}
        {downloaded && (
          <p className="archive-ready" role="status">
            Archive received and handed to your browser. Verify the ZIP is saved
            before deleting.
          </p>
        )}
        {error && (
          <p role="alert" className="alert alert-danger notice error">
            {error}
          </p>
        )}
        <p className="archive-retention">
          Deletion removes the workspace from active use. Durable execution and
          usage records are retained. Finish or cancel unfinished jobs first.
        </p>
        {!downloaded && (
          <label className="archive-skip">
            <input
              className="form-check-input"
              type="checkbox"
              checked={skip}
              disabled={exporting || deleting}
              onChange={(e) => setSkip(e.target.checked)}
            />{" "}
            I choose to delete without downloading an archive.
          </label>
        )}
        <div className="actions archive-dialog-actions">
          <button
            type="button"
            className="btn btn-outline-primary action secondary"
            disabled={deleting}
            onClick={close}
          >
            {exporting ? "Cancel archive & keep workspaces" : "Keep workspaces"}
          </button>
          <button
            type="button"
            className="btn btn-primary action archive-download"
            disabled={exporting || deleting}
            onClick={() => void archive()}
          >
            <CommandIcon label="Downloads" />
            {downloaded ? "Download again" : "Archive & download"}
          </button>
          <button
            type="button"
            className="btn btn-danger action archive-delete"
            disabled={exporting || deleting || (!downloaded && !skip)}
            onClick={async () => {
              setError("");
              setPhase("deleting");
              try {
                await onDelete();
                dialog.current?.close();
              } catch (e) {
                setError(
                  e instanceof Error
                    ? e.message
                    : "Deletion failed. Refresh to verify workspace state.",
                );
                setPhase(downloaded ? "ready" : "idle");
              }
            }}
          >
            {deleting ? "Deleting..." : "Delete workspaces"}
          </button>
        </div>
      </dialog>
    </>
  );
}
