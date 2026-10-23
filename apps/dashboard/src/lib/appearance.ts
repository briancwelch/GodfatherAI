import type { CSSProperties } from "react";

export interface Palette {
  background: string;
  foreground: string;
  card: string;
  muted: string;
  muted_foreground: string;
  border: string;
  primary: string;
  primary_foreground: string;
  sidebar: string;
  focus: string;
  header: string;
  header_text: string;
  highlight: string;
}
export interface Appearance {
  light: Palette;
  dark: Palette;
  default_theme: "light" | "dark";
  font: "system" | "arial" | "verdana" | "georgia" | "mono";
  font_size: number;
  line_height: number;
  density: "compact" | "comfortable" | "spacious";
  navigation_width: number;
  inspector_width: number;
  radius: number;
  content_width: "full" | "1440" | "1680";
  navigation_open: boolean;
  inspector_open: boolean;
  striped_tables: boolean;
  sticky_header: boolean;
  reduced_motion: boolean;
  ribbon_size: "normal" | "compact";
  button_variant: "solid" | "outline";
  control_size: "small" | "medium" | "large";
  panel_shadow: "none" | "small" | "medium";
  panel_padding: number;
  table_hover: boolean;
  table_borders: boolean;
  toast_position: "top-start" | "top-end" | "bottom-start" | "bottom-end";
  toast_width: number;
  progress_height: number;
  progress_striped: boolean;
  progress_animated: boolean;
  success_color: string;
  warning_color: string;
  danger_color: string;
  info_color: string;
}
export const defaults: Appearance = {
  light: {
    background: "#f4f8fc",
    foreground: "#14283d",
    card: "#ffffff",
    muted: "#e8f0f7",
    muted_foreground: "#52677d",
    border: "#d4dfe9",
    primary: "#077582",
    primary_foreground: "#ffffff",
    sidebar: "#f4f8fc",
    focus: "#087f8c",
    header: "#14283d",
    header_text: "#f4f8fc",
    highlight: "#58d5de",
  },
  dark: {
    background: "#141414",
    foreground: "#f4f8fc",
    card: "#202020",
    muted: "#2b2b2b",
    muted_foreground: "#b6c8d9",
    border: "#444444",
    primary: "#58d5de",
    primary_foreground: "#14283d",
    sidebar: "#1b1b1b",
    focus: "#58d5de",
    header: "#202020",
    header_text: "#f4f8fc",
    highlight: "#58d5de",
  },
  default_theme: "light",
  font: "system",
  font_size: 13,
  line_height: 1.5,
  density: "compact",
  navigation_width: 190,
  inspector_width: 250,
  radius: 3,
  content_width: "full",
  navigation_open: true,
  inspector_open: false,
  striped_tables: false,
  sticky_header: false,
  reduced_motion: false,
  ribbon_size: "normal",
  button_variant: "solid",
  control_size: "medium",
  panel_shadow: "small",
  panel_padding: 20,
  table_hover: true,
  table_borders: false,
  toast_position: "bottom-end",
  toast_width: 380,
  progress_height: 12,
  progress_striped: true,
  progress_animated: true,
  success_color: "#198754",
  warning_color: "#ffc107",
  danger_color: "#dc3545",
  info_color: "#0dcaf0",
};
export const fonts = {
  system: '"Segoe UI", system-ui, sans-serif',
  arial: "Arial, Helvetica, sans-serif",
  verdana: "Verdana, sans-serif",
  georgia: "Georgia, serif",
  mono: 'Consolas, "Courier New", monospace',
};
export const paletteLabels: Record<keyof Palette, string> = {
  background: "Workspace",
  foreground: "Text",
  card: "Panel",
  muted: "Selected / muted surface",
  muted_foreground: "Secondary text",
  border: "Borders",
  primary: "Actions / links",
  primary_foreground: "Action text",
  sidebar: "Navigation surface",
  focus: "Focus ring",
  header: "Application bar",
  header_text: "Application bar text",
  highlight: "Brand highlight",
};
export function appearanceStyle(
  settings: Appearance,
  theme: "light" | "dark",
): CSSProperties {
  settings = { ...defaults, ...settings };
  const palette = settings[theme];
  const rgb = (hex: string) =>
    [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(", ");
  const variables: Record<string, string | number> = {
    "--bs-primary-rgb": rgb(palette.primary),
    "--gf-control-font":
      settings.control_size === "small"
        ? "0.875em"
        : settings.control_size === "large"
          ? "1.125em"
          : "1em",
    "--gf-control-padding":
      settings.control_size === "small"
        ? "0.3rem 0.6rem"
        : settings.control_size === "large"
          ? "0.7rem 1rem"
          : "0.5rem 0.8rem",
    "--gf-button-bg":
      settings.button_variant === "outline" ? "transparent" : palette.primary,
    "--gf-button-color":
      settings.button_variant === "outline"
        ? palette.primary
        : palette.primary_foreground,
    "--gf-panel-shadow":
      settings.panel_shadow === "none"
        ? "none"
        : settings.panel_shadow === "small"
          ? "0 0.125rem 0.25rem #00000013"
          : "0 0.5rem 1rem #00000026",
    "--gf-panel-padding": settings.panel_padding + "px",
    "--gf-table-hover": settings.table_hover ? palette.muted : palette.card,
    "--gf-table-border-width": settings.table_borders ? "1px" : "0px",
    "--gf-table-stripe": settings.striped_tables
      ? palette.muted
      : "transparent",
    "--gf-toast-width": settings.toast_width + "px",
    "--gf-toast-top": settings.toast_position.startsWith("top")
      ? "16px"
      : "auto",
    "--gf-toast-bottom": settings.toast_position.startsWith("bottom")
      ? "44px"
      : "auto",
    "--gf-toast-left": settings.toast_position.endsWith("start")
      ? "16px"
      : "auto",
    "--gf-toast-right": settings.toast_position.endsWith("end")
      ? "16px"
      : "auto",
    "--gf-progress-height": settings.progress_height + "px",
    "--gf-progress-stripes": settings.progress_striped
      ? "linear-gradient(45deg, #ffffff26 25%, transparent 25%, transparent 50%, #ffffff26 50%, #ffffff26 75%, transparent 75%, transparent)"
      : "none",
    "--gf-progress-animation":
      settings.progress_animated && !settings.reduced_motion
        ? "progress-bar-stripes 1s linear infinite"
        : "none",
  };
  for (const name of ["success", "warning", "danger", "info"] as const) {
    const color = settings[`${name}_color`];
    variables[`--bs-${name}`] = color;
    variables[`--bs-${name}-rgb`] = rgb(color);
    variables[`--gf-${name}-text`] =
      contrast(color, "#ffffff") >= 4.5 ? "#ffffff" : "#000000";
  }
  for (const [key, value] of Object.entries(settings[theme]))
    variables[`--${key.replaceAll("_", "-")}`] = value;
  return {
    ...variables,
    "--ui-font": fonts[settings.font],
    "--ui-font-size": `${settings.font_size}px`,
    "--ui-line-height": settings.line_height,
    "--ui-navigation-width": `${settings.navigation_width}px`,
    "--ui-inspector-width": `${settings.inspector_width}px`,
    "--radius": `${settings.radius}px`,
    "--ui-content-width":
      settings.content_width === "full"
        ? "none"
        : `${settings.content_width}px`,
    "--ui-cell-padding":
      settings.density === "compact"
        ? "7px 9px"
        : settings.density === "comfortable"
          ? "11px 12px"
          : "15px 14px",
  } as CSSProperties;
}
export function contrast(a: string, b: string): number {
  function luminance(color: string) {
    const c = [1, 3, 5]
      .map((i) => parseInt(color.slice(i, i + 2), 16) / 255)
      .map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722;
  }
  const values = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (values[1] + 0.05) / (values[0] + 0.05);
}
export function paletteErrors(p: Palette): string[] {
  const pairs: [keyof Palette, (keyof Palette)[]][] = [
    ["foreground", ["background", "card", "sidebar", "muted"]],
    ["muted_foreground", ["background", "card", "sidebar"]],
    ["primary", ["background", "card", "sidebar", "muted"]],
    ["primary_foreground", ["primary"]],
    ["header_text", ["header"]],
    ["highlight", ["header"]],
  ];
  return pairs.flatMap(([ink, surfaces]) =>
    surfaces
      .filter((surface) => contrast(p[ink], p[surface]) < 4.5)
      .map(
        (surface) =>
          `${paletteLabels[ink]} on ${paletteLabels[surface]} needs 4.5:1 contrast.`,
      ),
  );
}
