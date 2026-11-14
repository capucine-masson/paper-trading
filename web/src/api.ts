import type {
  DashboardData,
  DecisionView,
  ForecastView,
  PortfolioData,
  Status,
} from "./types";

const DATA_DIR = "data/";
const NO_DATA_MESSAGE = "No data available yet. Please check back after the next agent cycle.";

async function load<T>(file: string): Promise<T> {
  const response = await fetch(`${DATA_DIR}${file}`, { cache: "no-store" });
  const isJson = response.headers.get("content-type")?.includes("json") ?? false;
  if (!response.ok || !isJson) {
    console.error(`Could not load ${file} (HTTP ${response.status}, json: ${isJson})`);
    throw new Error(NO_DATA_MESSAGE);
  }
  return (await response.json()) as T;
}

export const isDemo = (): boolean =>
  import.meta.env.DEV && new URLSearchParams(window.location.search).has("demo");

export async function loadDashboard(): Promise<DashboardData> {
  if (import.meta.env.DEV && isDemo()) {
    return (await import("./demo")).buildDemoData();
  }
  const [status, portfolio, decisions, forecasts] = await Promise.all([
    load<Status>("status.json"),
    load<PortfolioData>("portfolio.json"),
    load<DecisionView[]>("decisions.json"),
    load<ForecastView[]>("forecasts.json"),
  ]);
  return { status, portfolio, decisions, forecasts };
}

export const EXPORT_LINKS: { label: string; file: string }[] = [
  { label: "Decisions CSV", file: "decisions.csv" },
  { label: "Equity CSV", file: "equity.csv" },
  { label: "Forecasts CSV", file: "forecasts.csv" },
  { label: "Decisions JSON", file: "decisions.json" },
  { label: "Portfolio JSON", file: "portfolio.json" },
  { label: "Status JSON", file: "status.json" },
];

export function exportUrl(file: string): string {
  return `${DATA_DIR}${file}`;
}
