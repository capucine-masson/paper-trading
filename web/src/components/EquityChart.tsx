import { useState, type MouseEvent } from "react";
import { formatDateTime, formatUsd } from "../format";
import { ALL_SYMBOLS, type EquityPoint } from "../types";
import { Empty } from "./Feedback";

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 300;
// Smallest vertical gap (fraction of the plot) between two axis labels before one is hidden.
const AXIS_LABEL_GAP = 0.08;
const MIN_POINTS = 2;
const PADDING_RATIO = 0.08;
const TOOLTIP_FLIP_AT = 0.6;
const GRID_FRACTIONS = [0.25, 0.5, 0.75];
/** The capital floor is drawn once the lowest value is within this share of the gap between start and floor. */
const FLOOR_PROXIMITY = 0.25;

export interface OrderMark {
  symbol: string;
  action: string;
  price: number | null;
  qty: number | null;
}

interface Props {
  points: EquityPoint[];
  symbol: string;
  startValue: number;
  capitalFloor: number;
  orders: Map<string, OrderMark[]>;
}

interface SeriesPoint {
  point: EquityPoint;
  value: number;
}

const linePath = (xs: number[], ys: number[]): string =>
  xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${(ys[i] ?? 0).toFixed(1)}`).join(" ");

function markClass(marks: OrderMark[]): string {
  const actions = new Set(marks.map((m) => m.action));
  if (actions.size > 1) return "mark";
  return actions.has("buy") ? "mark mark-buy" : "mark mark-sell";
}

function markLabel(mark: OrderMark, withQuantity: boolean): string {
  const quantity = withQuantity && mark.qty !== null ? ` ${mark.qty}` : "";
  const price = mark.price === null ? "" : ` @ ${formatUsd(mark.price)}`;
  return `${mark.symbol} ${mark.action}${quantity}${price}`;
}

/**
 * One point per cycle on a category axis: nights and weekends leave no gap.
 * "All" plots the portfolio value; a symbol plots that symbol's price (its own buy and hold).
 */
export function EquityChart({ points, symbol, startValue, capitalFloor, orders }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const isAll = symbol === ALL_SYMBOLS;
  const series: SeriesPoint[] = points.flatMap((point) => {
    const value = isAll ? point.equity : point.prices[symbol];
    return value === undefined ? [] : [{ point, value }];
  });
  if (series.length < MIN_POINTS) {
    return <Empty message="Not enough data yet to draw a curve." />;
  }
  const last = series.length - 1;
  const xFraction = (i: number) => i / last;

  const referenced = isAll ? series.flatMap((s, i) => (s.point.buy_and_hold === null ? [] : [i])) : [];
  const lowest = Math.min(...series.map((s) => s.value));
  const floorIsNear = isAll && lowest - capitalFloor <= FLOOR_PROXIMITY * (startValue - capitalFloor);
  const values = [
    ...series.map((s) => s.value),
    ...referenced.map((i) => series[i]?.point.buy_and_hold ?? startValue),
    ...(isAll ? [startValue] : []),
    ...(floorIsNear ? [capitalFloor] : []),
  ];
  const [low, high] = [Math.min(...values), Math.max(...values)];
  const pad = Math.max(high - low, 1e-9) * PADDING_RATIO;
  const [bottom, top] = [low - pad, high + pad];
  const yFraction = (v: number) => (top - v) / (top - bottom);
  const y = (v: number) => yFraction(v) * VIEW_HEIGHT;
  const nearStart = (v: number) => isAll && Math.abs(yFraction(v) - yFraction(startValue)) < AXIS_LABEL_GAP;
  const xs = series.map((_, i) => xFraction(i) * VIEW_WIDTH);

  const onMove = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const fraction = Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1);
    setHover(Math.round(fraction * last));
  };

  const active = hover === null ? null : (series[hover] ?? null);
  const activeMarks = active === null ? [] : (orders.get(active.point.cycle_id) ?? []);
  const activeX = hover === null ? 0 : xFraction(hover);
  const tooltipSide =
    activeX > TOOLTIP_FLIP_AT ? { right: `${(1 - activeX) * 100}%` } : { left: `${activeX * 100}%` };
  return (
    <figure className="equity-chart">
      <div
        className="plot"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label={isAll ? "Portfolio value at each cycle, with the order markers" : `${symbol} price at each cycle`}
      >
        <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} preserveAspectRatio="none">
          {GRID_FRACTIONS.map((f) => (
            <line key={f} x1={0} x2={VIEW_WIDTH} y1={f * VIEW_HEIGHT} y2={f * VIEW_HEIGHT} className="grid-line" />
          ))}
          {isAll && <line x1={0} x2={VIEW_WIDTH} y1={y(startValue)} y2={y(startValue)} className="line-start" />}
          {floorIsNear && (
            <line x1={0} x2={VIEW_WIDTH} y1={y(capitalFloor)} y2={y(capitalFloor)} className="line-floor" />
          )}
          {referenced.length >= MIN_POINTS && (
            <path
              d={linePath(
                referenced.map((i) => xs[i] ?? 0),
                referenced.map((i) => y(series[i]?.point.buy_and_hold ?? startValue)),
              )}
              className="line-reference"
            />
          )}
          <path d={linePath(xs, series.map((s) => y(s.value)))} className="line-equity" />
        </svg>
        {!nearStart(high) && <span className="axis axis-top">{formatUsd(high)}</span>}
        {!nearStart(low) && <span className="axis axis-bottom">{formatUsd(low)}</span>}
        {isAll && (
          <span className="axis axis-right" style={{ top: `${yFraction(startValue) * 100}%` }}>
            Start {formatUsd(startValue)}
          </span>
        )}
        {floorIsNear && (
          <span className="axis axis-right axis-floor" style={{ top: `${yFraction(capitalFloor) * 100}%` }}>
            Capital floor {formatUsd(capitalFloor)}
          </span>
        )}
        {series.map((s, i) => {
          const marks = orders.get(s.point.cycle_id);
          if (marks === undefined) return null;
          return (
            <span
              key={s.point.cycle_id}
              className={markClass(marks)}
              style={{ left: `${xFraction(i) * 100}%`, top: `${yFraction(s.value) * 100}%` }}
              title={marks.map((m) => markLabel(m, !isAll)).join(", ")}
            />
          );
        })}
        {active !== null && (
          <>
            <div className="crosshair" style={{ left: `${activeX * 100}%` }} />
            <div className="tooltip" style={tooltipSide}>
              <strong>{formatDateTime(active.point.t)}</strong>
              <span>
                {isAll ? "Agent" : symbol} {formatUsd(active.value)}
              </span>
              {isAll && active.point.buy_and_hold !== null && (
                <span>Buy &amp; hold {formatUsd(active.point.buy_and_hold)}</span>
              )}
              {activeMarks.map((m) => (
                <span key={markLabel(m, true)}>Order: {markLabel(m, !isAll)}</span>
              ))}
            </div>
          </>
        )}
      </div>
      <figcaption className="chart-caption">
        <span>{formatDateTime(series[0]?.point.t ?? "")}</span>
        <span>{formatDateTime(series[last]?.point.t ?? "")}</span>
      </figcaption>
    </figure>
  );
}
