import type { DecisionView, ForecastPath } from "./types";

export const MACRO_LABELS: Record<string, string> = {
  brent: "Brent",
  us10y: "US 10Y",
  us2y: "US 2Y",
  dollar: "Dollar",
  vix: "VIX",
  hy_spread: "HY spread",
};

/** Median move over the forecast horizon, relative to the last price. */
export const expectedMove = (forecast: ForecastPath, price: number): number =>
  (forecast.median[forecast.median.length - 1] ?? price) / price - 1;

/** Width of the 80% range at the end of the horizon, relative to the median. */
export function rangeWidth(forecast: ForecastPath): number {
  const median = forecast.median[forecast.median.length - 1] ?? 1;
  return ((forecast.upper[forecast.upper.length - 1] ?? median) - (forecast.lower[forecast.lower.length - 1] ?? median)) / median;
}

/** The most recent decision that carries a forecast, for each symbol. */
export function latestForecasts(decisions: DecisionView[]): Map<string, DecisionView> {
  const latest = new Map<string, DecisionView>();
  for (const d of decisions) {
    if (d.forecast !== null && d.price !== null) latest.set(d.symbol, d);
  }
  return latest;
}
