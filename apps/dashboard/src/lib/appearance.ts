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
  const variables: Record<string, string | number> = {};
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
