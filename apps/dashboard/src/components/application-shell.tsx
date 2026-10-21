"use client";

import {
  Children,
  cloneElement,
  isValidElement,
  useState,
  type ReactNode,
} from "react";
import { CommandIcon } from "./command-icon";
import type { Snapshot } from "../lib/contracts";

export const navigation = {
  overview: "Overview",
  jobs: "Jobs",
  nodes: "Nodes",
  agents: "Agents",
  models: "Models",
  providers: "Provider Connections",
  activity: "Activity / Audit",
  administration: "Administration",
};

export function RibbonGroup({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="ribbon-group">
      <div className="actions">
        {Children.map(children, (child) => {
          if (
            isValidElement<{ children?: ReactNode }>(child) &&
            ["button", "a"].includes(String(child.type)) &&
            typeof child.props.children === "string"
          )
            return cloneElement(
              child,
              {},
              <>
                <CommandIcon label={child.props.children} />
                {child.props.children}
              </>,
            );
          return child;
        })}
      </div>
      <small>{label}</small>
    </div>
  );
}

export function UnavailableCommand({
  label,
  reason,
}: {
  label: string;
  reason: string;
}) {
  return (
    <span
      className="unavailable-command"
      tabIndex={0}
      title={reason}
      aria-label={`${label}: ${reason}`}
    >
      <button disabled className="action secondary">
        <CommandIcon label={label} />
        {label}
      </button>
      <span className="command-reason">{reason}</span>
    </span>
  );
}

export function ApplicationShell({
  section,
  data,
  account,
  stale,
  refresh,
  ribbon,
  children,
}: {
  section: keyof typeof navigation;
  data?: Snapshot | null;
  account?: { display_name: string; roles: string[] } | null;
  stale?: boolean;
  refresh: () => void;
  ribbon?: ReactNode;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [inspector, setInspector] = useState(false);
  return (
    <div
      className={`desktop-application ${collapsed ? "navigation-collapsed" : ""}`}
    >
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="application-bar">
        <a className="app-brand" href="/">
          THE GODFATHER <span>Command Center</span>
        </a>
        <span className="environment-label">
          {data?.environment
            ? `${data.environment} environment`
            : "Environment unavailable"}
        </span>
        <div className="account-controls">
          {account && <a href="/providers">Account settings</a>}
          {account && (
            <span>
              {account.display_name} · {account.roles.join(", ")}
            </span>
          )}
          <label>
            Theme
            <select
              aria-label="Theme"
              defaultValue="light"
              onChange={(e) => {
                document.documentElement.dataset.theme = e.target.value;
              }}
            >
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
          {account && (
            <button
              className="action secondary"
              onClick={async () => {
                const response = await fetch("/api/auth/logout", {
                  method: "POST",
                });
                if (response.ok) window.location.assign("/");
                else
                  window.alert(
                    "Logout not confirmed; retry when the API is available.",
                  );
              }}
            >
              Sign out
            </button>
          )}
        </div>
      </header>
      <nav className="application-tabs" aria-label="Main navigation">
        {Object.entries(navigation).map(([key, label]) => (
          <a
            key={key}
            href={key === "overview" ? "/" : `/${key}`}
            aria-current={key === section ? "page" : undefined}
          >
            {label}
          </a>
        ))}
      </nav>
      <div
        className="application-ribbon"
        role="region"
        aria-label={`${navigation[section]} ribbon`}
      >
        <RibbonGroup label="Data">
          <button className="action secondary" onClick={refresh}>
            Refresh
          </button>
        </RibbonGroup>
        {ribbon}
        <div id="section-ribbon" />
        <RibbonGroup label="Workspace layout">
          <button
            className="action secondary"
            aria-pressed={!collapsed}
            onClick={() => setCollapsed(!collapsed)}
          >
            Navigation
          </button>
          <button
            className="action secondary"
            aria-pressed={inspector}
            onClick={() => setInspector(!inspector)}
          >
            Inspector
          </button>
        </RibbonGroup>
      </div>
      <div className="application-workspace">
        {!collapsed && (
          <aside
            className="utility-panel navigation-panel"
            aria-label="Workspace navigation"
          >
            <h2>Explorer</h2>
            <p className="muted">
              {data?.workspaces.find((w) => w.id === data.workspace_id)?.name ||
                "Authorized workspaces"}
            </p>
            <nav>
              {Object.entries(navigation).map(([key, label]) => (
                <a
                  key={key}
                  href={key === "overview" ? "/" : `/${key}`}
                  aria-current={key === section ? "page" : undefined}
                >
                  <CommandIcon label={label} />
                  {label}
                </a>
              ))}
            </nav>
            <small>
              Drag the panel edge to resize. Use Navigation to collapse.
            </small>
          </aside>
        )}
        <div className="application-content">{children}</div>
        {inspector && (
          <aside
            className="utility-panel context-panel"
            aria-label="Workspace inspector"
          >
            <h2>Workspace inspector</h2>
            <dl>
              <dt>Section</dt>
              <dd>{navigation[section]}</dd>
              <dt>Workspace</dt>
              <dd>
                {data?.workspaces.find((w) => w.id === data.workspace_id)
                  ?.name || "Unavailable"}
              </dd>
              <dt>Environment</dt>
              <dd>{data?.environment || "Unavailable"}</dd>
              <dt>Access</dt>
              <dd>{account?.roles.join(", ") || "Sign-in required"}</dd>
            </dl>
            <p>
              Select a record in the working area to inspect its configuration
              and history.
            </p>
          </aside>
        )}
      </div>
      <footer className="application-status" role="status">
        <span
          title={
            data?.release?.built_at
              ? `Built ${new Date(data.release.built_at).toLocaleString()}`
              : "Build timestamp unavailable"
          }
        >
          {data?.release?.version
            ? `${data.release.version} · ${data.release.revision?.slice(0, 8) || "commit unavailable"}`
            : "Release metadata unavailable"}
          {data?.environment ? ` · ${data.environment}` : ""}
        </span>
        <span>
          {stale
            ? "Connection interrupted · displayed data may be stale"
            : data
              ? "Connected · authenticated backend"
              : "Connecting to authenticated backend"}
        </span>
        <span>
          {data
            ? `Updated ${new Date(data.generated_at).toLocaleString()}`
            : "No operational data loaded"}
        </span>
      </footer>
    </div>
  );
}
