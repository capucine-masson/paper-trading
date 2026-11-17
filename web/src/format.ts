const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 });
const percentTwoDecimals = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const signedPercentTwoDecimals = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const percentOneDecimal = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const signedPercent = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const shares = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
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

const time = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const day = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric" });

export const formatDay = (iso: string): string => day.format(new Date(iso));
export const formatTime = (iso: string): string => `${time.format(new Date(iso))} UTC`;
export const formatUsd = (value: number): string => usd.format(value);
export const formatShares = (value: number): string => shares.format(value);
export const formatSignedUsd = (value: number): string =>
  `${value > 0 ? "+" : ""}${usd.format(value)}`;
export const formatPercent = (value: number): string => percent.format(value);
export const formatPercentTwo = (value: number): string => percentTwoDecimals.format(value);
export const formatSignedPercentTwo = (value: number): string => signedPercentTwoDecimals.format(value);
export const formatPercentOne = (value: number): string => percentOneDecimal.format(value);
export const formatSignedPercent = (value: number): string => signedPercent.format(value);
export const formatDrawdown = (value: number): string =>
  value === 0 ? percent.format(0) : `-${percent.format(value)}`;
export const formatDateTime = (iso: string): string => `${dateTime.format(new Date(iso))} UTC`;
export const formatDate = (iso: string): string => date.format(new Date(iso));
