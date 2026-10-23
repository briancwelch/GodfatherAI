import type { Appearance } from "../lib/appearance";

export function BootstrapSettings({
  draft,
  change,
  disabled,
}: {
  draft: Appearance;
  change: <K extends keyof Appearance>(key: K, value: Appearance[K]) => void;
  disabled: boolean;
}) {
  return (
    <fieldset disabled={disabled} className="bootstrap-settings">
      <legend>Bootstrap components</legend>
      <p>
        Shared component defaults. Colors, typography, corner radius, table
        density and layout are configured above. Errors and active work stay
        visible until dismissed or resolved.
      </p>
      <div className="appearance-grid">
        <label>
          Button style
          <select
            className="form-select"
            aria-label="Button style"
            value={draft.button_variant}
            onChange={(e) =>
              change(
                "button_variant",
                e.target.value as Appearance["button_variant"],
              )
            }
          >
            <option value="solid">Solid</option>
            <option value="outline">Outline</option>
          </select>
        </label>
        <label>
          Control size
          <select
            className="form-select"
            aria-label="Control size"
            value={draft.control_size}
            onChange={(e) =>
              change(
                "control_size",
                e.target.value as Appearance["control_size"],
              )
            }
          >
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
          </select>
        </label>
        <label>
          Panel shadow
          <select
            className="form-select"
            aria-label="Panel shadow"
            value={draft.panel_shadow}
            onChange={(e) =>
              change(
                "panel_shadow",
                e.target.value as Appearance["panel_shadow"],
              )
            }
          >
            <option value="none">None</option>
            <option value="small">Small</option>
            <option value="medium">Medium</option>
          </select>
        </label>
        <label>
          Toast position
          <select
            className="form-select"
            aria-label="Toast position"
            value={draft.toast_position}
            onChange={(e) =>
              change(
                "toast_position",
                e.target.value as Appearance["toast_position"],
              )
            }
          >
            <option value="top-start">Top left</option>
            <option value="top-end">Top right</option>
            <option value="bottom-start">Bottom left</option>
            <option value="bottom-end">Bottom right</option>
          </select>
        </label>
        {(
          [
            ["panel_padding", "Panel padding (px)", 12, 32],
            ["toast_width", "Toast width (px)", 280, 560],
            ["progress_height", "Progress bar height (px)", 8, 24],
          ] as const
        ).map(([key, label, min, max]) => (
          <label key={key}>
            {label}
            <input
              className="form-control"
              type="number"
              required
              min={min}
              max={max}
              value={draft[key]}
              onChange={(e) => change(key, Number(e.target.value))}
            />
          </label>
        ))}
        {(
          [
            ["success_color", "Success color"],
            ["warning_color", "Warning color"],
            ["danger_color", "Error / danger color"],
            ["info_color", "Information color"],
          ] as const
        ).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              className="form-control form-control-color"
              type="color"
              value={draft[key]}
              onChange={(e) => change(key, e.target.value)}
            />
            <code>{draft[key]}</code>
          </label>
        ))}
        {(
          [
            ["table_hover", "Highlight table rows on hover"],
            ["table_borders", "Border table cells"],
            ["progress_striped", "Striped progress bars"],
            ["progress_animated", "Animate progress stripes"],
          ] as const
        ).map(([key, label]) => (
          <label key={key}>
            <input
              className="form-check-input"
              type="checkbox"
              checked={draft[key]}
              onChange={(e) => change(key, e.target.checked)}
            />
            {label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
