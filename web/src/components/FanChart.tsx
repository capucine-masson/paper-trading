import { formatUsd } from "../format";
import type { ForecastPath } from "../types";

const VIEW_WIDTH = 400;
const VIEW_HEIGHT = 110;
const PADDING_RATIO = 0.1;
const BAR_HOURS = 1;

const toPath = (xs: number[], ys: number[]): string =>
  xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${(ys[i] ?? 0).toFixed(1)}`).join(" ");

interface Props {
  forecast: ForecastPath;
  price: number;
}

/** Median and 10%-90% band, anchored at the price known when the forecast was made. */
export function FanChart({ forecast, price }: Props) {
  const median = [price, ...forecast.median];
  const lower = [price, ...forecast.lower];
  const upper = [price, ...forecast.upper];
  const [low, high] = [Math.min(...lower, price), Math.max(...upper, price)];
  const pad = Math.max(high - low, 1e-9) * PADDING_RATIO;
  const y = (v: number) => VIEW_HEIGHT - ((v - (low - pad)) / (high - low + 2 * pad)) * VIEW_HEIGHT;
  const xs = median.map((_, i) => (i / (median.length - 1)) * VIEW_WIDTH);
  const backwards = toPath([...xs].reverse(), [...lower].reverse().map(y)).replace(/^M/, "L");
  const band = `${toPath(xs, upper.map(y))} ${backwards} Z`;
  const last = median.length - 1;
  return (
    <figure className="fan">
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Forecast fan chart: median and 10% to 90% band"
      >
        <line x1={0} x2={VIEW_WIDTH} y1={y(price)} y2={y(price)} className="fan-price" />
        <path d={band} className="fan-band" />
        <path d={toPath(xs, median.map(y))} className="fan-median" />
      </svg>
      <figcaption className="fan-caption">
        <span>Now {formatUsd(price)}</span>
        <span>
          +{last * BAR_HOURS}h: 10% {formatUsd(lower[last] ?? price)} / median {formatUsd(median[last] ?? price)} / 90%{" "}
          {formatUsd(upper[last] ?? price)}
        </span>
      </figcaption>
    </figure>
  );
}
