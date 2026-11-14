import { useCallback, useEffect, useState } from "react";
import { ALL_SYMBOLS, type Period, type Theme } from "./types";

const THEME_KEY = "theme";
const PERIODS: Period[] = ["1d", "3d", "all"];

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
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      storeTheme(next);
      return next;
    });
  }, []);
  return [theme, toggle];
}

interface ViewState {
  period: Period;
  symbol: string;
}

function readUrl(): ViewState {
  const params = new URLSearchParams(window.location.search);
  const period = params.get("period");
  return {
    period: PERIODS.includes(period as Period) ? (period as Period) : "all",
    symbol: params.get("symbol") ?? ALL_SYMBOLS,
  };
}

export function useViewState(): [ViewState, (next: Partial<ViewState>) => void] {
  const [state, setState] = useState<ViewState>(readUrl);
  const update = useCallback((next: Partial<ViewState>) => {
    setState((current) => {
      const merged = { ...current, ...next };
      const params = new URLSearchParams();
      if (merged.period !== "all") params.set("period", merged.period);
      if (merged.symbol !== ALL_SYMBOLS) params.set("symbol", merged.symbol);
      const query = params.toString();
      window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
      return merged;
    });
  }, []);
  return [state, update];
}
