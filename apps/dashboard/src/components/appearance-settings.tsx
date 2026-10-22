"use client";

import { useEffect, useState, type FormEvent } from "react";
import { control } from "../lib/control-client";
import {
  appearanceStyle,
  defaults,
  fonts,
  paletteLabels,
  paletteErrors,
  type Appearance,
  type Palette,
} from "../lib/appearance";

export function AppearanceSettings() {
  const [draft, setDraft] = useState<Appearance | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    control<Appearance>("appearance")
      .then((data) => {
        if (active) setDraft(data);
      })
      .catch((e) => {
        if (active)
          setError(e instanceof Error ? e.message : "Appearance unavailable.");
      });
    return () => {
      active = false;
    };
  }, []);
  const errors = draft
    ? [
        ...paletteErrors(draft.light).map((e) => `Light: ${e}`),
        ...paletteErrors(draft.dark).map((e) => `Dark: ${e}`),
      ]
    : [];
  function change<K extends keyof Appearance>(key: K, value: Appearance[K]) {
    setDraft((current) => (current ? { ...current, [key]: value } : null));
    setMessage("");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await control<Appearance>("appearance", draft);
      setDraft(saved);
      window.dispatchEvent(
        new CustomEvent("godfather-appearance", { detail: saved }),
      );
      setMessage(
        "Site appearance saved. Other open sessions refresh within 30 seconds.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save not confirmed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel appearance-settings" aria-label="Site appearance">
      <h2>Site appearance</h2>
      <p>
        Platform administrators set the shared site defaults. Preview changes
        here, then save to apply them. Each browser can still choose light or
        dark.
      </p>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {!draft ? (
        <p role="status">
          {error
            ? "Appearance could not be loaded. Refresh to retry."
            : "Loading saved appearance..."}
        </p>
      ) : (
        <form onSubmit={save}>
          <fieldset disabled={busy}>
            <legend>Colors</legend>
            <label>
              Palette to edit{" "}
              <select
                value={theme}
                onChange={(e) => setTheme(e.target.value as "light" | "dark")}
              >
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <div className="appearance-grid">
              {(Object.keys(paletteLabels) as (keyof Palette)[]).map((key) => (
                <label key={key}>
                  {paletteLabels[key]}
                  <input
                    type="color"
                    value={draft[theme][key]}
                    onChange={(e) =>
                      change(theme, { ...draft[theme], [key]: e.target.value })
                    }
                  />
                  <code>{draft[theme][key]}</code>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset disabled={busy}>
            <legend>Typography and layout</legend>
            <div className="appearance-grid">
              <label>
                Default theme
                <select
                  value={draft.default_theme}
                  onChange={(e) =>
                    change("default_theme", e.target.value as "light" | "dark")
                  }
                >
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                </select>
              </label>
              <label>
                Font
                <select
                  value={draft.font}
                  onChange={(e) =>
                    change("font", e.target.value as Appearance["font"])
                  }
                >
                  {Object.keys(fonts).map((font) => (
                    <option key={font}>{font}</option>
                  ))}
                </select>
              </label>
              {(
                [
                  ["font_size", "Font size (px)", 12, 18, 1],
                  ["line_height", "Line height", 1.3, 1.8, 0.1],
                  ["navigation_width", "Navigation width (px)", 150, 360, 10],
                  ["inspector_width", "Inspector width (px)", 180, 360, 10],
                  ["radius", "Corner radius (px)", 0, 16, 1],
                ] as const
              ).map(([key, label, min, max, step]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    required
                    value={draft[key]}
                    min={min}
                    max={max}
                    step={step}
                    onChange={(e) => change(key, Number(e.target.value))}
                  />
                </label>
              ))}
              <label>
                Table density
                <select
                  value={draft.density}
                  onChange={(e) =>
                    change("density", e.target.value as Appearance["density"])
                  }
                >
                  {["compact", "comfortable", "spacious"].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                Content width
                <select
                  value={draft.content_width}
                  onChange={(e) =>
                    change(
                      "content_width",
                      e.target.value as Appearance["content_width"],
                    )
                  }
                >
                  <option value="full">Full width</option>
                  <option value="1440">1440 px</option>
                  <option value="1680">1680 px</option>
                </select>
              </label>
              <label>
                Ribbon size
                <select
                  value={draft.ribbon_size}
                  onChange={(e) =>
                    change(
                      "ribbon_size",
                      e.target.value as Appearance["ribbon_size"],
                    )
                  }
                >
                  <option value="normal">Normal</option>
                  <option value="compact">Compact</option>
                </select>
              </label>
              {(
                [
                  ["navigation_open", "Navigation open by default"],
                  ["inspector_open", "Inspector open by default"],
                  ["striped_tables", "Striped table rows"],
                  ["sticky_header", "Keep application bar visible"],
                  ["reduced_motion", "Reduce motion"],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={draft[key]}
                    onChange={(e) => change(key, e.target.checked)}
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <section
            className="appearance-preview"
            aria-label="Appearance preview"
            style={appearanceStyle(draft, theme)}
          >
            <div className="preview-header">
              THE GODFATHER <span>Command Center</span>
            </div>
            <div className="preview-workspace">
              <aside>
                Explorer
                <br />
                <a href="#appearance-preview-table">Overview</a>
              </aside>
              <div>
                <h3>Preview - {theme}</h3>
                <p>
                  Readable text,{" "}
                  <span className="muted">secondary information</span> and{" "}
                  <a href="#appearance-preview-table">actions</a>.
                </p>
                <button type="button" className="action">
                  Example action
                </button>
                <table id="appearance-preview-table">
                  <tbody>
                    {["Online computer", "Queued job"].map((label) => (
                      <tr key={label}>
                        <td>{label}</td>
                        <td>Example</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
          {!!errors.length && (
            <div role="alert" className="notice error">
              <p>Adjust these colors before saving:</p>
              <ul>
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="actions">
            <button className="action" disabled={busy || !!errors.length}>
              {busy ? "Saving..." : "Save site appearance"}
            </button>
            <button
              type="button"
              className="action secondary"
              disabled={busy}
              onClick={() => {
                setDraft(structuredClone(defaults));
                setMessage(
                  "Default settings loaded into preview. Save to apply them.",
                );
              }}
            >
              Reset preview to defaults
            </button>
          </div>
        </form>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
