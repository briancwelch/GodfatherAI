"use client";

import { useRef, useState, type ReactNode } from "react";
import type { AuditEvent } from "../lib/contracts";
import { localTime, short } from "../lib/contracts";

export function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`status status-${value.toLowerCase()}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: ReactNode;
  detail?: string;
}) {
  return (
    <article className="metric">
      <p>{label}</p>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}

export function DataTable<T>({
  caption,
  rows,
  columns,
  rowKey,
  selectedKey,
  onSelect,
}: {
  caption: string;
  rows: T[];
  columns: { label: string; cell: (row: T) => ReactNode }[];
  rowKey: (row: T) => string;
  selectedKey?: string;
  onSelect?: (row: T) => void;
}) {
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label={caption}
    >
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.label} scope="col">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              aria-selected={onSelect ? selectedKey === rowKey(row) : undefined}
              onClick={onSelect ? () => onSelect(row) : undefined}
            >
              {columns.map((c) => (
                <td key={c.label}>{c.cell(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="empty">No matching records.</p>}
    </div>
  );
}

export function JsonDetails({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  return (
    <details className="json-details">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function EventTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="timeline">
      {events.map((event) => (
        <li key={event.id}>
          <div>
            <StatusBadge value={event.severity} />
            <strong>{event.type}</strong>
            <time dateTime={event.created_at}>
              {localTime(event.created_at)}
            </time>
          </div>
          <p>
            {event.job_id && (
              <a href={`/jobs/${event.job_id}`}>Job {short(event.job_id)}</a>
            )}{" "}
            {event.node_id && (
              <a href={`/nodes/${event.node_id}`}>
                Node {short(event.node_id)}
              </a>
            )}{" "}
            {event.attempt_id && <span>Attempt {short(event.attempt_id)}</span>}{" "}
            {event.actor_id && <span>Actor {short(event.actor_id)}</span>}
          </p>
          <JsonDetails label="Event details" value={event.details} />
        </li>
      ))}
      {!events.length && (
        <li className="empty">No recorded events in this view.</li>
      )}
    </ol>
  );
}

export function ConfirmAction({
  label,
  description,
  onConfirm,
}: {
  label: string;
  description: string;
  onConfirm: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <>
      <button
        type="button"
        className="action secondary"
        onClick={() => {
          setError("");
          dialog.current?.showModal();
        }}
      >
        {label}
      </button>
      <dialog
        ref={dialog}
        aria-label={label}
        onCancel={(event) => {
          if (busy) event.preventDefault();
        }}
      >
        <h2>{label}</h2>
        <p>{description}</p>
        {error && <p role="alert">{error}</p>}
        <div className="actions">
          <button
            type="button"
            className="action secondary"
            disabled={busy}
            onClick={() => dialog.current?.close()}
          >
            Keep current state
          </button>
          <button
            type="button"
            className="action"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
                dialog.current?.close();
              } catch {
                setError(
                  "Action failed or permission denied. Refresh to verify backend state.",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Waiting for backend…" : `Confirm ${label.toLowerCase()}`}
          </button>
        </div>
      </dialog>
    </>
  );
}

export function Pager({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        {total === 0
          ? "0 records"
          : `${offset + 1}–${Math.min(offset + limit, total)} of ${total}`}
      </span>
      <button
        className="action secondary"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        Previous page
      </button>
      <button
        className="action secondary"
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        Next page
      </button>
    </div>
  );
}
