"use client";

import { useFeedback } from "./toast-notifications";

import { UserName } from "./node-identity";
import { useId, useRef, useState, type ReactNode } from "react";
import type { AuditEvent } from "../lib/contracts";
import { localTime, short } from "../lib/contracts";

export function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`badge status status-${value.toLowerCase()}`}>
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
    <article className="card metric">
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
  selection,
}: {
  caption: string;
  rows: T[];
  columns: { label: string; cell: (row: T) => ReactNode }[];
  rowKey: (row: T) => string;
  selectedKey?: string;
  onSelect?: (row: T) => void;
  selection?: {
    ids: string[];
    key: (row: T) => string;
    label: (row: T) => string;
    eligible: (row: T) => boolean;
    onChange: (ids: string[]) => void;
    disabled: boolean;
  };
}) {
  const selectable = selection
    ? [...new Set(rows.filter(selection.eligible).map(selection.key))]
    : [];
  const allSelected =
    selectable.length > 0 &&
    selectable.every((id) => selection?.ids.includes(id));
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label={caption}
    >
      <table className="table align-middle">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {selection && (
              <th scope="col">
                <input
                  className="form-check-input"
                  type="checkbox"
                  aria-label={`Select all eligible ${caption.toLowerCase()} on this page`}
                  checked={allSelected}
                  disabled={selection.disabled || !selectable.length}
                  onChange={() =>
                    selection.onChange(allSelected ? [] : selectable)
                  }
                />
              </th>
            )}
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
              {selection && (
                <td onClick={(e) => e.stopPropagation()}>
                  <input
                    className="form-check-input"
                    type="checkbox"
                    aria-label={`Select ${selection.label(row)}`}
                    checked={selection.ids.includes(selection.key(row))}
                    disabled={selection.disabled || !selection.eligible(row)}
                    onChange={(e) =>
                      selection.onChange(
                        e.target.checked
                          ? [...selection.ids, selection.key(row)]
                          : selection.ids.filter(
                              (id) => id !== selection.key(row),
                            ),
                      )
                    }
                  />
                </td>
              )}
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
            {event.actor_id && (
              <span>
                Actor{" "}
                <UserName
                  id={event.actor_id}
                  name={event.actor_name}
                  picture={event.actor_picture}
                />
              </span>
            )}
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
  disabled = false,
}: {
  disabled?: boolean;
  label: string;
  description: string;
  onConfirm: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useFeedback(error);
  return (
    <>
      <button
        type="button"
        className="btn btn-outline-primary action secondary"
        disabled={disabled}
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
            className="btn btn-outline-primary action secondary"
            disabled={busy}
            onClick={() => dialog.current?.close()}
          >
            Keep current state
          </button>
          <button
            type="button"
            className="btn btn-primary action"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
                dialog.current?.close();
              } catch (e) {
                setError(
                  e instanceof Error
                    ? e.message
                    : "Action failed. Refresh to verify backend state.",
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
        type="button"
        className="btn btn-outline-primary action secondary"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
      >
        Previous page
      </button>
      <button
        type="button"
        className="btn btn-outline-primary action secondary"
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        Next page
      </button>
    </div>
  );
}

export function SectionTabs({
  label,
  tabs,
  value,
  onChange,
}: {
  label: string;
  tabs: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div
      className="nav nav-tabs section-tabs"
      role="tablist"
      aria-label={label}
    >
      {tabs.map((tab, index) => (
        <button
          className="btn btn-outline-primary nav-link"
          key={tab}
          type="button"
          role="tab"
          id={`${id}-${index}`}
          aria-selected={value === tab}
          tabIndex={value === tab ? 0 : -1}
          onClick={() => onChange(tab)}
          onKeyDown={(event) => {
            const target =
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? tabs.length - 1
                  : event.key === "ArrowRight"
                    ? (index + 1) % tabs.length
                    : event.key === "ArrowLeft"
                      ? (index + tabs.length - 1) % tabs.length
                      : null;
            if (target !== null) {
              event.preventDefault();
              onChange(tabs[target]);
              document.getElementById(`${id}-${target}`)?.focus();
            }
          }}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
