"use client";

import { useState } from "react";
import { notifyToast } from "../lib/notifications";

const staticVariables = [
  ["workspace.id", "Current workspace ID"],
  ["workspace.name", "Current workspace name"],
  ["job.name", "Task group name"],
  ["job.goal", "Shared goal"],
  ["task.key", "This task's stable key"],
  ["task.name", "This task's name"],
  ["agent.id", "Selected agent ID"],
  ["agent.name", "Selected agent name"],
  ["agent.version", "Selected agent version"],
  ["model.identifier", "Agent's requested model"],
];
export function VariableLegend({
  drafts,
  customVariables = "",
}: {
  drafts: { key: string; name: string }[];
  customVariables?: string;
}) {
  const [open, setOpen] = useState(false);
  let custom: string[] = [];
  try {
    const parsed = JSON.parse(customVariables || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed))
      custom = Object.keys(parsed)
        .filter((key) => /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(key))
        .slice(0, 32);
  } catch {
    /* Invalid drafts are validated at submission. */
  }
  return (
    <div className="variable-legend">
      <button
        type="button"
        className="action secondary"
        aria-expanded={open}
        aria-controls="task-variable-legend"
        onClick={() => setOpen(!open)}
      >
        Variables
      </button>
      {open && (
        <section
          id="task-variable-legend"
          className="variable-popout"
          aria-label="Variable legend"
        >
          <h3>Available variables</h3>
          <p>
            Click a variable to copy. Paste it into task instructions. An output
            reference waits for that earlier task. Variables never execute code
            or grant access.
          </p>
          <ul>
            {[
              ...staticVariables,
              ...custom.map((key) => [`vars.${key}`, "Custom text variable"]),
              ...drafts.map((draft) => [
                `tasks.${draft.key}.output`,
                `${draft.name}: committed output (earlier tasks only)`,
              ]),
            ].map(([key, description]) => (
              <li key={key}>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(`{{${key}}}`);
                      notifyToast({
                        id: "variable-copy",
                        kind: "notification",
                        title: "Variable copied",
                        message: `{{${key}}}`,
                      });
                    } catch {
                      notifyToast({
                        id: "variable-copy",
                        kind: "error",
                        title: "Copy unavailable",
                        message: "Select and copy the variable text manually.",
                      });
                    }
                  }}
                >
                  <code>{`{{${key}}}`}</code>
                </button>
                <span>{description}</span>
              </li>
            ))}
          </ul>
          <p>
            <code>{"Add 2+2, then add {{tasks.task1.output}}"}</code>
          </p>
          <button
            type="button"
            className="action secondary"
            onClick={() => setOpen(false)}
          >
            Close variables
          </button>
        </section>
      )}
    </div>
  );
}
