import { formatDateTime } from "../format";
import { Empty } from "./Feedback";

export interface ChartPoint {
  t: string;
  value: number;
}

interface Props {
  points: ChartPoint[];
  formatValue: (value: number) => string;
  label: string;
}

const WIDTH = 640;
const HEIGHT = 220;
const PAD_X = 12;
const PAD_Y = 20;
const MIN_POINTS = 2;

export function LineChart({ points, formatValue, label }: Props) {
  if (points.length < MIN_POINTS) {
    return <Empty message="Not enough data yet to draw a curve." />;
  }
  const times = points.map((p) => new Date(p.t).getTime());
  const values = points.map((p) => p.value);
  const [t0, t1] = [Math.min(...times), Math.max(...times)];
  const [v0, v1] = [Math.min(...values), Math.max(...values)];
  const x = (t: number) => PAD_X + ((t - t0) / Math.max(t1 - t0, 1)) * (WIDTH - 2 * PAD_X);
  const y = (v: number) => HEIGHT - PAD_Y - ((v - v0) / Math.max(v1 - v0, 1e-9)) * (HEIGHT - 2 * PAD_Y);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(times[i] ?? t0)},${y(p.value)}`).join(" ");
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label}>
        <path d={path} className="chart-line" fill="none" />
        {points.map((p, i) => (
          <circle key={p.t} cx={x(times[i] ?? t0)} cy={y(p.value)} r={3} className="chart-dot">
            <title>{`${formatDateTime(p.t)}: ${formatValue(p.value)}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="chart-caption">
        <span>
          {formatDateTime(points[0]?.t ?? "")} to {formatDateTime(points[points.length - 1]?.t ?? "")}
        </span>
        <span>
          Low {formatValue(v0)} / High {formatValue(v1)}
        </span>
      </figcaption>
    </figure>
  );
}
