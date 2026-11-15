import { formatDay, formatUsd } from "../format";
import type { ForecastPoint } from "../types";
import { Empty } from "./Feedback";

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 300;
const MIN_POINTS = 2;
const PADDING_RATIO = 0.08;
const GRID_FRACTIONS = [0.25, 0.5, 0.75];
const HOUR_MS = 3_600_000;
const TICK_COUNT = 5;

interface Props {
  symbol: string;
  forecasts: ForecastPoint[];
  horizonBars: number;
}

const isOutside = (point: ForecastPoint): boolean => point.actual < point.lower || point.actual > point.upper;

const linePath = (xs: number[], ys: number[]): string =>
  xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${(ys[i] ?? 0).toFixed(1)}`).join(" ");

/** Each forecast is drawn where it was meant to land: its decision time plus the horizon. */
export function ForecastFan({ symbol, forecasts, horizonBars }: Props) {
  const fallback = forecasts[0];
  if (fallback === undefined || forecasts.length < MIN_POINTS) {
    return <Empty message={`Not enough past forecasts for ${symbol} to draw the chart.`} />;
  }
  const last = forecasts.length - 1;
  const values = forecasts.flatMap((f) => [f.lower, f.upper, f.actual]);
  const [low, high] = [Math.min(...values), Math.max(...values)];
  const pad = Math.max(high - low, 1e-9) * PADDING_RATIO;
  const [bottom, top] = [low - pad, high + pad];
  const yFraction = (v: number) => (top - v) / (top - bottom);
  const y = (v: number) => yFraction(v) * VIEW_HEIGHT;
  const xs = forecasts.map((_, i) => (i / last) * VIEW_WIDTH);
  const upperEdge = linePath(xs, forecasts.map((f) => y(f.upper)));
  const lowerEdge = linePath([...xs].reverse(), forecasts.map((f) => y(f.lower)).reverse()).replace(/^M/, "L");
  const targetIso = (point: ForecastPoint): string =>
    new Date(new Date(point.t).getTime() + horizonBars * HOUR_MS).toISOString();
  const ticks = Array.from({ length: TICK_COUNT }, (_, k) => Math.round((k / (TICK_COUNT - 1)) * last));
  const misses = forecasts.flatMap((f, i) => (isOutside(f) ? [{ f, i }] : []));
  return (
    <figure className="equity-chart forecast-fan">
      <div className="plot" role="img" aria-label={`${symbol}: real price against the forecast 80% range`}>
        <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} preserveAspectRatio="none">
          {GRID_FRACTIONS.map((f) => (
            <line key={f} x1={0} x2={VIEW_WIDTH} y1={f * VIEW_HEIGHT} y2={f * VIEW_HEIGHT} className="grid-line" />
          ))}
          <path d={`${upperEdge} ${lowerEdge} Z`} className="fan-band" />
          <path d={linePath(xs, forecasts.map((f) => y(f.median)))} className="line-median" />
          <path d={linePath(xs, forecasts.map((f) => y(f.actual)))} className="line-equity" />
        </svg>
        <span className="axis axis-top">{formatUsd(high)}</span>
        <span className="axis axis-bottom">{formatUsd(low)}</span>
        {misses.map(({ f, i }) => (
          <span
            key={f.t}
            className="miss-dot"
            style={{ left: `${(i / last) * 100}%`, top: `${yFraction(f.actual) * 100}%` }}
            title={`${formatDay(targetIso(f))}: real ${formatUsd(f.actual)}, range ${formatUsd(f.lower)} to ${formatUsd(f.upper)}`}
          />
        ))}
      </div>
      <div className="x-ticks" aria-hidden="true">
        {ticks.map((index, k) => (
          <span
            key={index}
            style={{
              left: `${(index / last) * 100}%`,
              transform: `translateX(${k === 0 ? "0" : k === ticks.length - 1 ? "-100%" : "-50%"})`,
            }}
          >
            {formatDay(targetIso(forecasts[index] ?? fallback))}
          </span>
        ))}
      </div>
      <figcaption className="chart-caption">
        <span className="legend">
          <span>
            <i className="swatch swatch-actual" /> Real price
          </span>
          <span>
            <i className="swatch swatch-band" /> 80% range
          </span>
          <span>
            <i className="swatch swatch-median" /> Median
          </span>
          <span>
            <i className="swatch swatch-miss" /> Outside the range ({misses.length} of the {forecasts.length} shown)
          </span>
        </span>
      </figcaption>
    </figure>
  );
}
