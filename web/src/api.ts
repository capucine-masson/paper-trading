import type { BacktestReport, DashboardData, DecisionView, PortfolioData, Status } from "./types";

const DATA_DIR = "data/";
const NO_DATA_MESSAGE = "No data available yet. Please check back after the next agent cycle.";

async function fetchJson<T>(file: string): Promise<T | null> {
  const response = await fetch(`${DATA_DIR}${file}`, { cache: "no-store" });
  const isJson = response.headers.get("content-type")?.includes("json") ?? false;
  if (!response.ok || !isJson) {
    console.error(`Could not load ${file} (HTTP ${response.status}, json: ${isJson})`);
    return null;
  }
  return (await response.json()) as T;
}

async function load<T>(file: string): Promise<T> {
  const data = await fetchJson<T>(file);
  if (data === null) throw new Error(NO_DATA_MESSAGE);
  return data;
}

export const isDemo = (): boolean =>
  import.meta.env.DEV && new URLSearchParams(window.location.search).has("demo");

export async function loadDashboard(): Promise<DashboardData> {
  if (import.meta.env.DEV && isDemo()) {
    return (await import("./demo")).buildDemoData();
  }
  const [status, portfolio, decisions, backtest] = await Promise.all([
    load<Status>("status.json"),
    load<PortfolioData>("portfolio.json"),
    load<DecisionView[]>("decisions.json"),
    fetchJson<BacktestReport>("backtest.json"),
  ]);
  return { status, portfolio, decisions, backtest };
}

export const EXPORT_LINKS: { label: string; file: string }[] = [
  { label: "Trades CSV", file: "trades.csv" },
  { label: "Decisions CSV", file: "decisions.csv" },
  { label: "Equity CSV", file: "equity.csv" },
];

export function exportUrl(file: string): string {
  return `${DATA_DIR}${file}`;
}
