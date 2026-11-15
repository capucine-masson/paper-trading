import { formatDate, formatPercentOne } from "../format";
import { forSymbol } from "../filters";
import type { BacktestReport, ForecastMetrics } from "../types";
import { Empty } from "./Feedback";
import { ForecastFan } from "./ForecastFan";

const TARGET_COVERAGE = 0.8;
const COVERAGE_TOLERANCE = 0.05;
const NAIVE_RATIO = 1;
const SAME_TOLERANCE = 0.02;
const OVERALL = "All";
const BAR_UNIT = "hours";
const FAN_FORECASTS = 120;
const FAN_DEFAULT_SYMBOL = "SPY";
type Tone = "up" | "flat" | "down";
type Comparison = "better" | "same" | "worse";

interface Row {
  label: string;
  metrics: ForecastMetrics;
}

const COMPARISON_TONE: Record<Comparison, Tone> = { better: "up", same: "flat", worse: "down" };
const PILL_CLASS: Record<Comparison, string> = { better: "pill pill-buy", same: "pill", worse: "pill pill-sell" };
const PILL_LABEL: Record<Comparison, string> = { better: "Yes", same: "About equal", worse: "No" };

const HIT_RATE_TIP = "Share of forecasts where the real price ended inside the announced 80% range.";
const ERROR_TIP =
  'Average error of the median forecast, compared with the forecast "nothing changes" (the price stays where it is). Negative is better.';

const hitRateTone = (coverage: number): Tone =>
  Math.abs(coverage - TARGET_COVERAGE) <= COVERAGE_TOLERANCE ? "up" : "down";

const errorChange = (ratio: number): number => ratio - NAIVE_RATIO;

function compare(ratio: number): Comparison {
  const change = errorChange(ratio);
  if (change < -SAME_TOLERANCE) return "better";
  return change > SAME_TOLERANCE ? "worse" : "same";
}

const formatChange = (ratio: number): string => {
  const change = Number((errorChange(ratio) * 100).toFixed(1));
  return `${change > 0 ? "+" : ""}${change.toFixed(1)}%`;
};

interface Props {
  backtest: BacktestReport | null;
  symbol: string;
  onSymbol: (symbol: string) => void;
}

export function Quality({ backtest, symbol, onSymbol }: Props) {
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
  const { coverage, mae_ratio: ratio } = model.overall;
  const fanSymbol = backtest.symbols.includes(symbol)
    ? symbol
    : backtest.symbols.includes(FAN_DEFAULT_SYMBOL)
      ? FAN_DEFAULT_SYMBOL
      : (backtest.symbols[0] ?? FAN_DEFAULT_SYMBOL);
  const symbolForecasts = forSymbol(backtest.forecasts, fanSymbol).sort((a, b) => a.t.localeCompare(b.t));
  return (
    <div className="page-section quality-page">
      <div className="section-head">
        <h2>Forecast quality</h2>
        <span className="muted">
          We replayed {model.overall.n.toLocaleString("en-US")} past forecasts ({formatDate(backtest.history_start)} to{" "}
          {formatDate(backtest.history_end)}). Each one predicted the price {backtest.horizon_bars} {BAR_UNIT} ahead
          using only the data available at that moment, then was checked against what really happened. Model:{" "}
          {model.model}.
        </span>
      </div>
      <div className="quality-body">
        <div className="quality-side">
      <section className="card quality-summary">
        <p className={`summary-line ${hitRateTone(coverage)}`}>
          The 80% range held the real price {formatPercentOne(coverage)} of the time
          {hitRateTone(coverage) === "up" ? ": reliable." : ": not fully reliable."}
        </p>
        <AccuracySentence ratio={ratio} />
        <p className="muted">The wider the range, the smaller the position.</p>
      </section>
      <section className="card quality-details">
        <table className="quality-table">
          <thead>
            <tr>
              <th scope="col">Symbol</th>
              <th scope="col" title={HIT_RATE_TIP}>
                Real price within the range
                <small>target 80%</small>
              </th>
              <th scope="col" title={ERROR_TIP}>
                Better than guessing "no change"?
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <QualityRow key={row.label} row={row} />
            ))}
          </tbody>
        </table>
      </section>
        </div>
      <section className="card quality-chart">
        <div className="section-head">
          <h3>Chart: {fanSymbol}</h3>
          <select value={fanSymbol} onChange={(e) => onSymbol(e.target.value)} aria-label="Symbol">
            {backtest.symbols.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <ForecastFan
          symbol={fanSymbol}
          forecasts={symbolForecasts.slice(-FAN_FORECASTS)}
          horizonBars={backtest.horizon_bars}
        />
      </section>
      </div>
    </div>
  );
}

function AccuracySentence({ ratio }: { ratio: number | null }) {
  if (ratio === null) return <p className="summary-line">Accuracy vs "nothing changes" is not available.</p>;
  const comparison = compare(ratio);
  const wording: Record<Comparison, string> = {
    better: "Accuracy: better than",
    same: "Accuracy: about the same as",
    worse: "Accuracy: worse than",
  };
  return (
    <p className={`summary-line ${COMPARISON_TONE[comparison]}`}>
      {wording[comparison]} "nothing changes" (error differs by {formatChange(ratio)}).
    </p>
  );
}

function QualityRow({ row }: { row: Row }) {
  const { coverage, mae_ratio: ratio } = row.metrics;
  const inside = hitRateTone(coverage) === "up";
  return (
    <tr className={row.label === OVERALL ? "total-row" : undefined}>
      <th scope="row">{row.label}</th>
      <td>
        <span className="num-inline">{formatPercentOne(coverage)}</span>{" "}
        <span
          className={inside ? "status-ok" : "status-warn"}
          role="img"
          aria-label={inside ? "Within the target range" : "Outside the target range"}
          title={inside ? "Within 75-85%" : "Outside 75-85%"}
        >
          {inside ? "✓" : "▲"}
        </span>
      </td>
      <td>
        {ratio === null ? (
          <span className="muted">n/a</span>
        ) : (
          <span className={PILL_CLASS[compare(ratio)]} title={`Error vs guessing "no change": ${formatChange(ratio)}`}>
            {PILL_LABEL[compare(ratio)]}
          </span>
        )}
      </td>
    </tr>
  );
}
