import { formatDate, formatPercent } from "../format";
import type { BacktestReport, ForecastMetrics } from "../types";
import { Empty } from "./Feedback";

const TARGET_COVERAGE = 0.8;
const COVERAGE_TOLERANCE = 0.05;
const RATIO_SCALE_MAX = 1.5;
const NAIVE_RATIO = 1;
const OVERALL = "All";

interface Row {
  label: string;
  metrics: ForecastMetrics;
}

const calibrated = (coverage: number): boolean => Math.abs(coverage - TARGET_COVERAGE) <= COVERAGE_TOLERANCE;

export function Quality({ backtest }: { backtest: BacktestReport | null }) {
  const model = backtest?.models[0];
  if (backtest === null || model === undefined) {
    return (
      <div className="page-section">
        <h2>Forecast quality</h2>
        <Empty message="No backtest report yet. Run the backtest, then export." />
      </div>
    );
  }
  const rows: Row[] = [
    { label: OVERALL, metrics: model.overall },
    ...Object.entries(model.per_symbol)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([label, metrics]) => ({ label, metrics })),
  ];
  const coverage = model.overall.coverage;
  return (
    <div className="page-section">
      <div className="section-head">
        <h2>Forecast quality</h2>
        <span className="muted">
          Walk-forward backtest, {formatDate(backtest.history_start)} to {formatDate(backtest.history_end)},{" "}
          {model.overall.n.toLocaleString("en-US")} forecasts, horizon {backtest.horizon_bars} hourly bars. No
          look-ahead.
        </span>
      </div>
      <div className="quality-grid">
        <section className="card">
          <h3>Interval calibration</h3>
          <p className={`verdict-line ${calibrated(coverage) ? "up" : "down"}`}>
            The announced 80% interval contains the real price {formatPercent(coverage)} of the time
            {calibrated(coverage) ? ": well calibrated." : ": not calibrated."}
          </p>
          <ul className="bars">
            {rows.map((row) => (
              <Bar
                key={row.label}
                label={row.label}
                fraction={row.metrics.coverage}
                mark={TARGET_COVERAGE}
                text={formatPercent(row.metrics.coverage)}
                good={calibrated(row.metrics.coverage)}
              />
            ))}
          </ul>
          <p className="muted">Marker: 80% target. Within 5 points counts as calibrated.</p>
        </section>
        <section className="card">
          <h3>Error vs naive baseline</h3>
          <RatioVerdict ratio={model.overall.mae_ratio} />
          <ul className="bars">
            {rows.map((row) => (
              <Bar
                key={row.label}
                label={row.label}
                fraction={(row.metrics.mae_ratio ?? 0) / RATIO_SCALE_MAX}
                mark={NAIVE_RATIO / RATIO_SCALE_MAX}
                text={row.metrics.mae_ratio === null ? "n/a" : row.metrics.mae_ratio.toFixed(3)}
                good={row.metrics.mae_ratio !== null && row.metrics.mae_ratio < NAIVE_RATIO}
              />
            ))}
          </ul>
          <p className="muted">
            Mean absolute error of the median divided by that of the naive forecast "the price stays where it is".
            Marker: 1.0. Below it, Timestral beats the baseline.
          </p>
        </section>
      </div>
    </div>
  );
}

function RatioVerdict({ ratio }: { ratio: number | null }) {
  if (ratio === null) return <p className="verdict-line">Not available.</p>;
  const gap = formatPercent(Math.abs(NAIVE_RATIO - ratio));
  return ratio < NAIVE_RATIO ? (
    <p className="verdict-line up">Timestral beats the naive baseline by {gap}.</p>
  ) : (
    <p className="verdict-line down">Timestral does not beat the naive baseline: its error is {gap} higher.</p>
  );
}

interface BarProps {
  label: string;
  fraction: number;
  mark: number;
  text: string;
  good: boolean;
}

function Bar({ label, fraction, mark, text, good }: BarProps) {
  const width = Math.min(Math.max(fraction, 0), 1) * 100;
  return (
    <li className="bar-row">
      <span className="bar-label">{label}</span>
      <span className="bar-track">
        <span className={`bar-fill ${good ? "bar-good" : "bar-bad"}`} style={{ width: `${width}%` }} />
        <span className="bar-mark" style={{ left: `${mark * 100}%` }} />
      </span>
      <span className="bar-value num">{text}</span>
    </li>
  );
}
