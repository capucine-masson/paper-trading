import type { DecisionView, ForecastPath } from "./types";

const level = (value: number): string => value.toFixed(2);
const percentLevel = (value: number): string => `${level(value)}%`;

const MACRO_FORMATS: Record<string, { label: string; format: (value: number) => string }> = {
  brent: { label: "Brent oil", format: (value) => `$${level(value)}` },
  us10y: { label: "US 10-year yield", format: percentLevel },
  us2y: { label: "US 2-year yield", format: percentLevel },
  dollar: { label: "US dollar index", format: level },
  vix: { label: "VIX (market fear)", format: level },
  hy_spread: { label: "High-yield spread (credit stress)", format: percentLevel },
};

export function formatMacro(name: string, value: number): { label: string; value: string } {
  const known = MACRO_FORMATS[name];
  return known === undefined
    ? { label: name, value: level(value) }
    : { label: known.label, value: known.format(value) };
}

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
