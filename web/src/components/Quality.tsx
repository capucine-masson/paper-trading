import { formatDate, formatPercent } from "../format";
import { forSymbol } from "../filters";
import { ALL_SYMBOLS, type BacktestReport, type ForecastMetrics } from "../types";
import { DotPlot, type Tone } from "./DotPlot";
import { Empty } from "./Feedback";
import { ForecastFan } from "./ForecastFan";

const TARGET_COVERAGE = 0.8;
const COVERAGE_TOLERANCE = 0.05;
const NAIVE_RATIO = 1;
const SAME_TOLERANCE = 0.01;
const OVERALL = "All";
const BAR_UNIT = "hours";
const FAN_FORECASTS = 120;
const FAN_DEFAULT_SYMBOL = "SPY";
const HIT_AXIS = { min: 0.6, max: 1 };
const ERROR_AXIS = { min: -0.03, max: 0.03 };
type Comparison = "better" | "same" | "worse";

interface Row {
  label: string;
  metrics: ForecastMetrics;
}

const COMPARISON_TONE: Record<Comparison, Tone> = { better: "up", same: "flat", worse: "down" };

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
  const fanSymbol =
    symbol !== ALL_SYMBOLS
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
          The 80% range held the real price {formatPercent(coverage)} of the time
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
                Range hit rate (target {formatPercent(TARGET_COVERAGE)})
                <AxisHint low="60%" high="100%" />
              </th>
              <th scope="col" title={ERROR_TIP}>
                Error vs "nothing changes"
                <AxisHint low="-3%" high="+3%" />
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
          <h3>
            Chart: {fanSymbol}
            {symbol === ALL_SYMBOLS && " (choose a symbol to change)"}
          </h3>
          <select value={symbol} onChange={(e) => onSymbol(e.target.value)} aria-label="Symbol">
            <option value={ALL_SYMBOLS}>All symbols</option>
            {backtest.symbols.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <ForecastFan symbol={fanSymbol} forecasts={symbolForecasts.slice(-FAN_FORECASTS)}
          allForecasts={symbolForecasts}
          horizonBars={backtest.horizon_bars} />
      </section>
      </div>
    </div>
  );
}

function AxisHint({ low, high }: { low: string; high: string }) {
  return (
    <span className="axis-hint">
      <span>
        <span>{low}</span>
        <span>{high}</span>
      </span>
    </span>
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
      {wording[comparison]} "nothing changes" ({formatChange(ratio)} error).
    </p>
  );
}

function QualityRow({ row }: { row: Row }) {
  const { coverage, mae_ratio: ratio } = row.metrics;
  return (
    <tr className={row.label === OVERALL ? "total-row" : undefined}>
      <th scope="row">{row.label}</th>
      <td>
        <DotPlot
          value={coverage}
          {...HIT_AXIS}
          bandLow={TARGET_COVERAGE - COVERAGE_TOLERANCE}
          bandHigh={TARGET_COVERAGE + COVERAGE_TOLERANCE}
          tone={hitRateTone(coverage)}
          text={formatPercent(coverage)}
        />
      </td>
      <td>
        {ratio === null ? (
          <span className="muted">n/a</span>
        ) : (
          <DotPlot
            value={errorChange(ratio)}
            {...ERROR_AXIS}
            bandLow={-SAME_TOLERANCE}
            bandHigh={SAME_TOLERANCE}
            tone={COMPARISON_TONE[compare(ratio)]}
            text={`${formatChange(ratio)} ${compare(ratio)}`}
          />
        )}
      </td>
    </tr>
  );
}
