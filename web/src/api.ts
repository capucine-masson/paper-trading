import type {
  DashboardData,
  DecisionView,
  ForecastView,
  PortfolioData,
  Status,
} from "./types";

const DATA_DIR = "data/";

async function load<T>(file: string): Promise<T> {
  const response = await fetch(`${DATA_DIR}${file}`, { cache: "no-store" });
  const isJson = response.headers.get("content-type")?.includes("json") ?? false;
  if (!response.ok || !isJson) {
    throw new Error(
      `No data yet: ${file} was not found. It is created by the first cycle, or locally by "uv run python -m agent.export".`,
    );
  }
  return (await response.json()) as T;
}

export async function loadDashboard(): Promise<DashboardData> {
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
