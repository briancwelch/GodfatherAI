// Font Awesome Free 7, Fonticons, Inc.; CC BY 4.0. See FONT-AWESOME-LICENSE.txt.
import icons from "../lib/command-icons.json";

export function CommandIcon({ label }: { label: string }) {
  const mapping: [RegExp, keyof typeof icons][] = [
    [/warning|error/i, "warning"],
    [/verified|success/i, "verified"],
    [/notification/i, "notification"],
    [/tasks/i, "run"],
    [/refresh/i, "refresh"],
    [/invit/i, "invitations"],
    [/users|account/i, "users"],
    [/permission/i, "permissions"],
    [/workspace/i, "workspaces"],
    [/navigation|navigator/i, "navigation"],
    [/overview/i, "overview"],
    [/activity|audit/i, "activity"],
    [/provider|integration/i, "providers"],
    [/download/i, "downloads"],
    [/create|submit/i, "create"],
    [/edit|version/i, "edit"],
    [/run/i, "run"],
    [/inspect|capabilit/i, "inspect"],
    [/model/i, "models"],
    [/node/i, "nodes"],
    [/job/i, "jobs"],
    [/agent/i, "agents"],
    [/disable|enable/i, "disable"],
  ];
  const name =
    mapping.find(([pattern]) => pattern.test(label))?.[1] || "settings";
  const icon = icons[name as keyof typeof icons];
  return (
    <svg
      className="command-icon"
      aria-hidden="true"
      viewBox={`0 0 ${icon.Width} ${icon.Height}`}
      fill="currentColor"
    >
      <path d={icon.Data} />
    </svg>
  );
}
