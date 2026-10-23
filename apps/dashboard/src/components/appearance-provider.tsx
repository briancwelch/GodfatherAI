"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { appearanceStyle, defaults, type Appearance } from "../lib/appearance";
import { control } from "../lib/control-client";

const Context = createContext<{
  settings: Appearance;
  theme: "light" | "dark";
  setTheme: (theme: "light" | "dark") => void;
}>({
  settings: defaults,
  theme: defaults.default_theme,
  setTheme: () => {},
});
export const useAppearance = () => useContext(Context);
export function AppearanceProvider({
  enabled,
  children,
}: {
  enabled: boolean;
  children: ReactNode;
}) {
  const [settings, setSettings] = useState(defaults);
  const [override, setOverride] = useState<"light" | "dark" | null>(null);
  const theme = override || settings.default_theme;
  useEffect(() => {
    let active = true;
    // Read the browser preference after hydration without changing the server render.
    void Promise.resolve().then(() => {
      try {
        const stored = sessionStorage.getItem("godfather-theme");
        if (active && (stored === "dark" || stored === "light"))
          setOverride(stored);
      } catch {
        /* Browser storage may be disabled. */
      }
    });
    if (!enabled)
      return () => {
        active = false;
      };
    const refresh = () => {
      if (document.visibilityState !== "hidden")
        void control<Appearance>("appearance")
          .then((data) => {
            if (active) setSettings({ ...defaults, ...data });
          })
          .catch(() => {});
    };
    const update = (event: Event) =>
      setSettings((event as CustomEvent<Appearance>).detail);
    refresh();
    const timer = setInterval(refresh, 30000);
    window.addEventListener("godfather-appearance", update);
    window.addEventListener("focus", refresh);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener("godfather-appearance", update);
      window.removeEventListener("focus", refresh);
    };
  }, [enabled]);
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.bsTheme = theme;
    for (const [key, value] of Object.entries(appearanceStyle(settings, theme)))
      root.style.setProperty(key, String(value));
    root.dataset.stripes = String(settings.striped_tables);
    root.dataset.motion = settings.reduced_motion ? "reduced" : "normal";
    root.dataset.stickyHeader = String(settings.sticky_header);
    root.dataset.ribbonSize = settings.ribbon_size;
  }, [settings, theme]);
  return (
    <Context.Provider
      value={{
        settings,
        theme,
        setTheme: (next) => {
          setOverride(next);
          try {
            sessionStorage.setItem("godfather-theme", next);
          } catch {
            /* The current tab still retains its theme. */
          }
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
