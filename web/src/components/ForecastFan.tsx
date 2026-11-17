import { linePath, niceTicks } from "../chart";
import { formatDay, formatUsd, formatUsdRounded } from "../format";
import type { ForecastPoint } from "../types";
import { Empty } from "./Feedback";

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 300;
const MIN_POINTS = 2;
const PADDING_RATIO = 0.08;
const HOUR_MS = 3_600_000;
const TICK_COUNT = 5;

interface Props {
  symbol: string;
  forecasts: ForecastPoint[];
  horizonBars: number;
}

const isOutside = (point: ForecastPoint): boolean => point.actual < point.lower || point.actual > point.upper;

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
  const yTicks = niceTicks(bottom, top).values.map((value) => ({ value, fraction: yFraction(value) }));
  const ticks = Array.from({ length: TICK_COUNT }, (_, k) => Math.round((k / (TICK_COUNT - 1)) * last));
  const misses = forecasts.flatMap((f, i) => (isOutside(f) ? [{ f, i }] : []));
  return (
    <figure className="equity-chart forecast-fan">
      <div className="chart-body">
        <div className="y-axis" aria-hidden="true">
          {yTicks.map((t) => (
            <span key={t.value} className="tick" style={{ top: `${t.fraction * 100}%` }}>
              {formatUsdRounded(t.value)}
            </span>
          ))}
        </div>
        <div className="plot" role="img" aria-label={`${symbol}: real price against the forecast 80% range`}>
          <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} preserveAspectRatio="none">
            {yTicks.map((t) => (
              <line
                key={t.value}
                x1={0}
                x2={VIEW_WIDTH}
                y1={t.fraction * VIEW_HEIGHT}
                y2={t.fraction * VIEW_HEIGHT}
                className="grid-line"
              />
            ))}
            <path d={`${upperEdge} ${lowerEdge} Z`} className="fan-band" />
            <path d={linePath(xs, forecasts.map((f) => y(f.median)))} className="line-median" />
            <path d={linePath(xs, forecasts.map((f) => y(f.actual)))} className="line-equity" />
          </svg>
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
      </div>
      <div className="legend">
        <span>
          <i className="swatch swatch-actual" /> Real price
        </span>
        <span>
          <i className="swatch swatch-median" /> Median forecast
        </span>
        <span>
          <i className="swatch swatch-band" /> 80% forecast range
        </span>
        <span>
          <i className="swatch swatch-miss" /> Real price outside the range ({misses.length} of {forecasts.length})
        </span>
      </div>
    </figure>
  );
}
