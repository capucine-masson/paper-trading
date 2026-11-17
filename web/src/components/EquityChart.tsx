import { useState, type MouseEvent } from "react";
import { formatAxisTime, formatDateTime, formatUsd, formatUsdRounded } from "../format";
import { ALL_SYMBOLS, type EquityPoint } from "../types";
import { Empty } from "./Feedback";

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 300;
// Smallest vertical gap (fraction of the plot) between two axis labels before one is hidden.
const AXIS_LABEL_GAP = 0.12;
const MIN_POINTS = 2;
const PADDING_RATIO = 0.08;
const TOOLTIP_FLIP_AT = 0.6;
const TARGET_TICKS = 4;
const NICE_STEPS = [1, 2, 5, 10];
/** The capital floor is drawn once the lowest value is within this share of the gap between start and floor. */
const FLOOR_PROXIMITY = 0.25;
/** Height of the bar for the largest trade in view, and the floor that keeps the smallest one visible. */
const MAX_BAR_PX = 28;
const MIN_BAR_PX = 2;

export interface OrderMark {
  symbol: string;
  action: string;
  price: number | null;
  qty: number | null;
}

interface Props {
  points: EquityPoint[];
  /** Every point, whatever the period: the vertical scale is fitted to it so it does not move between periods. */
  scalePoints: EquityPoint[];
  symbol: string;
  startValue: number;
  capitalFloor: number;
  orders: Map<string, OrderMark[]>;
}

interface SeriesPoint {
  point: EquityPoint;
  value: number;
  reference: number | null;
}

/**
 * "All": portfolio value against the buy and hold benchmark.
 * A symbol: the agent's position value against the same capital held since its first buy;
 * before any buy there is nothing to compare, so the plain price is drawn.
 */
export function buildSeries(
  points: EquityPoint[],
  symbol: string,
): SeriesPoint[] {
  if (symbol === ALL_SYMBOLS) {
    return points.map((point) => ({
      point,
      value: point.equity,
      reference: point.buy_and_hold,
    }));
  }
  const priced = points.flatMap((point) => {
    const price = point.prices[symbol];
    return price === undefined
      ? []
      : [{ point, price, qty: point.positions[symbol] ?? 0 }];
  });
  const first = priced.findIndex((p) => p.qty > 0);
  const entry = priced[first];
  if (entry === undefined) {
    return priced.map(({ point, price }) => ({
      point,
      value: price,
      reference: null,
    }));
  }
  const capital = entry.qty * entry.price;
  return priced
    .slice(first)
    .map(({ point, price, qty }) => ({
      point,
      value: qty * price,
      reference: (capital * price) / entry.price,
    }));
}

/** Evenly spaced round values (1, 2 or 5 times a power of ten) that cover [bottom, top]. */
function niceTicks(bottom: number, top: number): { values: number[]; step: number } {
  const raw = (top - bottom) / TARGET_TICKS;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = (NICE_STEPS.find((n) => n * magnitude >= raw) ?? 10) * magnitude;
  const first = Math.ceil(bottom / step);
  const count = Math.floor(top / step) - first + 1;
  return { values: Array.from({ length: Math.max(count, 0) }, (_, i) => (first + i) * step), step };
}

const linePath = (xs: number[], ys: number[]): string =>
  xs
    .map(
      (x, i) =>
        `${i === 0 ? "M" : "L"}${x.toFixed(1)},${(ys[i] ?? 0).toFixed(1)}`,
    )
    .join(" ");

const volumeOf = (marks: OrderMark[], action: "buy" | "sell"): number =>
  marks.reduce(
    (sum, m) =>
      m.action === action && m.price !== null && m.qty !== null
        ? sum + m.price * m.qty
        : sum,
    0,
  );

function markLabel(mark: OrderMark, withQuantity: boolean): string {
  const quantity = withQuantity && mark.qty !== null ? ` ${mark.qty}` : "";
  const price = mark.price === null ? "" : ` @ ${formatUsd(mark.price)}`;
  return `${mark.symbol} ${mark.action}${quantity}${price}`;
}

/**
 * One point per cycle on a category axis: nights and weekends leave no gap.
 * "All" plots the portfolio value; a symbol plots that symbol's price (its own buy and hold).
 */
export function EquityChart({
  points,
  scalePoints,
  symbol,
  startValue,
  capitalFloor,
  orders,
}: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const isAll = symbol === ALL_SYMBOLS;
  const series = buildSeries(points, symbol);
  const tracksAgent = series.some((s) => s.reference !== null);
  if (series.length < MIN_POINTS) {
    return <Empty message="Not enough data yet to draw a curve." />;
  }
  const last = series.length - 1;
  const xFraction = (i: number) => i / last;

  const referenced = series.flatMap((s, i) =>
    s.reference === null ? [] : [i],
  );
  const scaleSeries = [...series, ...buildSeries(scalePoints, symbol)];
  const lowest = Math.min(...scaleSeries.map((s) => s.value));
  const floorIsNear =
    isAll &&
    lowest - capitalFloor <= FLOOR_PROXIMITY * (startValue - capitalFloor);
  const values = [
    ...scaleSeries.flatMap((s) => (s.reference === null ? [s.value] : [s.value, s.reference])),
    ...(isAll ? [startValue] : []),
    ...(floorIsNear ? [capitalFloor] : []),
  ];
  const [low, high] = [Math.min(...values), Math.max(...values)];
  const pad = Math.max(high - low, 1e-9) * PADDING_RATIO;
  const [bottom, top] = [low - pad, high + pad];
  const yFraction = (v: number) => (top - v) / (top - bottom);
  const y = (v: number) => yFraction(v) * VIEW_HEIGHT;
  const referenceFractions = [
    ...(isAll ? [yFraction(startValue)] : []),
    ...(floorIsNear ? [yFraction(capitalFloor)] : []),
  ];
  const { values: tickValues, step } = niceTicks(bottom, top);
  const ticks = tickValues
    .map((value) => ({ value, fraction: yFraction(value) }))
    .filter((t) => referenceFractions.every((r) => Math.abs(r - t.fraction) >= AXIS_LABEL_GAP));
  const formatTick = step >= 1 ? formatUsdRounded : formatUsd;
  const middleIndex = Math.round(last / 2);
  const middle = series[middleIndex];
  const xs = series.map((_, i) => xFraction(i) * VIEW_WIDTH);
  const maxVolume = Math.max(
    ...series.flatMap((s) => {
      const marks = orders.get(s.point.cycle_id) ?? [];
      return [volumeOf(marks, "buy"), volumeOf(marks, "sell")];
    }),
    1e-9,
  );

  const onMove = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const fraction = Math.min(
      Math.max((event.clientX - box.left) / box.width, 0),
      1,
    );
    setHover(Math.round(fraction * last));
  };

  const active = hover === null ? null : (series[hover] ?? null);
  const activeMarks =
    active === null ? [] : (orders.get(active.point.cycle_id) ?? []);
  const activeX = hover === null ? 0 : xFraction(hover);
  const tooltipSide =
    activeX > TOOLTIP_FLIP_AT
      ? { right: `${(1 - activeX) * 100}%` }
      : { left: `${activeX * 100}%` };
  return (
    <figure className="equity-chart">
      <div className="chart-body">
        <div className="y-axis" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t.value} className="tick" style={{ top: `${t.fraction * 100}%` }}>
              {formatTick(t.value)}
            </span>
          ))}
          {isAll && (
            <span
              className="tick tick-start"
              style={{ top: `${yFraction(startValue) * 100}%` }}
            >
              <small>Start</small>
              {formatUsd(startValue)}
            </span>
          )}
          {floorIsNear && (
            <span
              className="tick tick-floor"
              style={{ top: `${yFraction(capitalFloor) * 100}%` }}
            >
              <small>Capital floor</small>
              {formatUsd(capitalFloor)}
            </span>
          )}
        </div>
        <div
          className="plot"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={
            isAll
              ? "Portfolio value at each cycle, with the order markers"
              : `${symbol} ${tracksAgent ? "position value" : "price"} at each cycle`
          }
        >
          <svg
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            preserveAspectRatio="none"
          >
            {ticks.map((t) => (
              <line
                key={t.value}
                x1={0}
                x2={VIEW_WIDTH}
                y1={t.fraction * VIEW_HEIGHT}
                y2={t.fraction * VIEW_HEIGHT}
                className="grid-line"
              />
            ))}
            {isAll && (
              <line
                x1={0}
                x2={VIEW_WIDTH}
                y1={y(startValue)}
                y2={y(startValue)}
                className="line-start"
              />
            )}
            {floorIsNear && (
              <line
                x1={0}
                x2={VIEW_WIDTH}
                y1={y(capitalFloor)}
                y2={y(capitalFloor)}
                className="line-floor"
              />
            )}
            {referenced.length >= MIN_POINTS && (
              <path
                d={linePath(
                  referenced.map((i) => xs[i] ?? 0),
                  referenced.map((i) => y(series[i]?.reference ?? startValue)),
                )}
                className="line-reference"
              />
            )}
            <path
              d={linePath(
                xs,
                series.map((s) => y(s.value)),
              )}
              className={
                isAll || tracksAgent ? "line-equity" : "line-reference"
              }
            />
          </svg>
          {series.map((s, i) => {
            const marks = orders.get(s.point.cycle_id);
            if (marks === undefined) return null;
            return (
              <span
                key={s.point.cycle_id}
                className="volume-group"
                style={{
                  left: `${xFraction(i) * 100}%`,
                  top: `${yFraction(s.value) * 100}%`,
                }}
                title={marks.map((m) => markLabel(m, !isAll)).join(", ")}
              >
                {(["buy", "sell"] as const).map((action) => {
                  const volume = volumeOf(marks, action);
                  return volume > 0 ? (
                    <span
                      key={action}
                      className={`volume-bar volume-${action}`}
                      style={{
                        height: `${Math.max((volume / maxVolume) * MAX_BAR_PX, MIN_BAR_PX)}px`,
                      }}
                    />
                  ) : null;
                })}
              </span>
            );
          })}
          {active !== null && (
            <>
              <div
                className="crosshair"
                style={{ left: `${activeX * 100}%` }}
              />
              <div className="tooltip" style={tooltipSide}>
                <strong>{formatDateTime(active.point.t)}</strong>
                <span>
                  {tracksAgent ? "Agent" : symbol} {formatUsd(active.value)}
                </span>
                {active.reference !== null && (
                  <span>Buy &amp; hold {formatUsd(active.reference)}</span>
                )}
                {activeMarks.map((m) => (
                  <span key={markLabel(m, true)}>
                    Order: {markLabel(m, !isAll)}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
        <figcaption className="chart-caption">
          <span>{formatAxisTime(series[0]?.point.t ?? "")}</span>
          <span className="caption-middle" style={{ left: `${xFraction(middleIndex) * 100}%` }}>
            {formatAxisTime(middle?.point.t ?? "")}
          </span>
          <span>{formatAxisTime(series[last]?.point.t ?? "")}</span>
        </figcaption>
      </div>
    </figure>
  );
}
