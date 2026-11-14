const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 });
const signedPercent = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const dateTime = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const date = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  year: "numeric",
  month: "short",
  day: "numeric",
});

export const formatUsd = (value: number): string => usd.format(value);
export const formatSignedUsd = (value: number): string =>
  `${value > 0 ? "+" : ""}${usd.format(value)}`;
export const formatPercent = (value: number): string => percent.format(value);
export const formatSignedPercent = (value: number): string => signedPercent.format(value);
export const formatDateTime = (iso: string): string => `${dateTime.format(new Date(iso))} UTC`;
export const formatDate = (iso: string): string => date.format(new Date(iso));
