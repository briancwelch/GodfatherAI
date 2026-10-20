// Font Awesome Free 7, Fonticons, Inc.; CC BY 4.0. See FONT-AWESOME-LICENSE.txt.
import icons from "../lib/command-icons.json";

export function CommandIcon({ label }: { label: string }) {
  const name = /refresh/i.test(label)
    ? "refresh"
    : /create|submit/i.test(label)
      ? "create"
      : /edit|version/i.test(label)
        ? "edit"
        : /run/i.test(label)
          ? "run"
          : /navigation|workspace/i.test(label)
            ? "navigation"
            : /inspect|capabilit/i.test(label)
              ? "inspect"
              : /model/i.test(label)
                ? "models"
                : /node/i.test(label)
                  ? "nodes"
                  : /job/i.test(label)
                    ? "jobs"
                    : /disable|enable/i.test(label)
                      ? "disable"
                      : "settings";
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
