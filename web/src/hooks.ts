import { useCallback, useEffect, useState } from "react";
import { ALL_SYMBOLS, type Period, type Tab, type Theme } from "./types";

const THEME_KEY = "theme";
const PERIODS: Period[] = ["1d", "3d", "all"];
export const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "decisions", label: "Decisions" },
  { id: "quality", label: "Forecast quality" },
];

function readStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

function storeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // The page works without storage.
  }
}

function deviceTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => readStoredTheme() ?? deviceTheme());
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    storeTheme(next);
  }, [theme]);
  return [theme, toggle];
}

interface ViewState {
  tab: Tab;
  period: Period;
  symbol: string;
}

function readUrl(): ViewState {
  const params = new URLSearchParams(window.location.search);
  const period = params.get("period");
  const tab = params.get("tab");
  return {
    tab: TABS.some((t) => t.id === tab) ? (tab as Tab) : "overview",
    period: PERIODS.includes(period as Period) ? (period as Period) : "all",
    symbol: params.get("symbol") ?? ALL_SYMBOLS,
  };
}

function writeUrl(state: ViewState): void {
  const params = new URLSearchParams(window.location.search);
  const setOrDrop = (key: string, value: string, fallback: string) =>
    value === fallback ? params.delete(key) : params.set(key, value);
  setOrDrop("tab", state.tab, "overview");
  setOrDrop("period", state.period, "all");
  setOrDrop("symbol", state.symbol, ALL_SYMBOLS);
  const query = params.toString();
  window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

export function useViewState(): [ViewState, (next: Partial<ViewState>) => void] {
  const [state, setState] = useState<ViewState>(readUrl);
  useEffect(() => writeUrl(state), [state]);
  const update = useCallback(
    (next: Partial<ViewState>) => setState((current) => ({ ...current, ...next })),
    [],
  );
  return [state, update];
}
