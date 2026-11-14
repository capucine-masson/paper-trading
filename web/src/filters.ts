import { ALL_SYMBOLS, type Period } from "./types";

const HOUR_MS = 3_600_000;
const PERIOD_HOURS: Record<Exclude<Period, "all">, number> = { "1d": 24, "3d": 72 };

/** Keep items inside the period, counted back from the last exported data (not from now). */
export function inPeriod<T extends { t: string }>(
  items: T[],
  period: Period,
  referenceIso: string,
): T[] {
  if (period === "all") return items;
  const start = new Date(referenceIso).getTime() - PERIOD_HOURS[period] * HOUR_MS;
  return items.filter((item) => new Date(item.t).getTime() >= start);
}

export function forSymbol<T extends { symbol: string }>(items: T[], symbol: string): T[] {
  return symbol === ALL_SYMBOLS ? items : items.filter((item) => item.symbol === symbol);
}

export function latestPerSymbol<T extends { symbol: string }>(items: T[]): T[] {
  const latest = new Map<string, T>();
  for (const item of items) latest.set(item.symbol, item);
  return [...latest.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
}
