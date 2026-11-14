import type { RuleUnit } from "./types";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 });
const dateTime = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export const formatUsd = (value: number): string => usd.format(value);
export const formatPercent = (value: number): string => percent.format(value);
export const formatDateTime = (iso: string): string => `${dateTime.format(new Date(iso))} UTC`;

export function formatRuleValue(value: number, unit: RuleUnit): string {
  if (unit === "usd") return formatUsd(value);
  if (unit === "ratio") return formatPercent(value);
  return String(value);
}
