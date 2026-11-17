import { formatDate, formatPercentOne, formatPercentTwo, formatSignedPercentTwo } from "../format";
import { forSymbol } from "../filters";
import type { BacktestReport, StrategyResult } from "../types";
import { Empty } from "./Feedback";
import { ForecastFan } from "./ForecastFan";

const TARGET_COVERAGE = 0.8;
const COVERAGE_TOLERANCE = 0.05;
const NAIVE_RATIO = 1;
const SAME_TOLERANCE = 0.02;
const BAR_UNIT = "hours";
const FAN_FORECASTS = 120;
const FAN_DEFAULT_SYMBOL = "SPY";
const PERCENT_SCALE = 100;
const AGENT_NAME_MARKER = "the agent";
type Tone = "up" | "flat" | "down";
type Comparison = "better" | "same" | "worse";

const COMPARISON_TONE: Record<Comparison, Tone> = { better: "up", same: "flat", worse: "down" };

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

const returnTone = (value: number): Tone => (value === 0 ? "flat" : value > 0 ? "up" : "down");

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
  const { coverage, mae_ratio: ratio, direction_hit_rate: direction } = model.overall;
  const fanSymbol = backtest.symbols.includes(symbol)
    ? symbol
    : backtest.symbols.includes(FAN_DEFAULT_SYMBOL)
      ? FAN_DEFAULT_SYMBOL
      : (backtest.symbols[0] ?? FAN_DEFAULT_SYMBOL);
  const symbolMetrics = model.per_symbol[fanSymbol];
  const symbolForecasts = forSymbol(backtest.forecasts, fanSymbol).sort((a, b) => a.t.localeCompare(b.t));
  return (
    <div className="page-section quality-page">
      <div className="section-head">
        <h2>Forecast quality</h2>
        <span className="muted">
          Backtest run on {formatDate(backtest.generated_at)}: {model.overall.n.toLocaleString("en-US")} forecasts
          made between {formatDate(backtest.decision_start)} and {formatDate(backtest.history_end)} (after the model's
          release, to avoid look-ahead), each {backtest.horizon_bars} {BAR_UNIT} ahead using only past data. Model:{" "}
          {model.model}.
        </span>
      </div>
      <div className="quality-body">
        <div className="quality-side">
          <section className="card quality-summary">
            <p className={`summary-line ${hitRateTone(coverage) === "up" ? "flat" : "down"}`}>
              The price stayed inside the forecast range {formatPercentOne(coverage)} of the time. It should be 80%
              {hitRateTone(coverage) === "up"
                ? ", so the range is well sized."
                : coverage < TARGET_COVERAGE
                  ? ", so the model is slightly overconfident."
                  : ", so the model is slightly underconfident."}
            </p>
            <AccuracySentence ratio={ratio} />
            {direction !== null && (
              <p className="summary-line flat">
                It guessed the direction right {formatPercentOne(direction)} of the time (almost random).
              </p>
            )}
          </section>
          <section className="card quality-details">
            <table className="quality-table">
              <thead>
                <tr>
                  <th scope="col">Strategy</th>
                  <th scope="col">Return</th>
                  <th scope="col">Max drawdown</th>
                  <th scope="col">Avg exposure</th>
                </tr>
              </thead>
              <tbody>
                {backtest.strategies.map((strategy) => (
                  <StrategyRow key={strategy.name} strategy={strategy} />
                ))}
              </tbody>
            </table>
            <p className="muted quality-note">
              Same rules and simulated costs for all: differences are noise, not skill.
            </p>
          </section>
        </div>
        <section className="card quality-chart">
          <div className="section-head">
            <h3>Forecast vs real price</h3>
            <select value={fanSymbol} onChange={(e) => onSymbol(e.target.value)} aria-label="Symbol">
              {backtest.symbols.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            {symbolMetrics !== undefined && <SymbolStats symbol={fanSymbol} coverage={symbolMetrics.coverage} />}
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

function StrategyRow({ strategy }: { strategy: StrategyResult }) {
  const isAgent = strategy.name.includes(AGENT_NAME_MARKER);
  const value = strategy.return_pct / PERCENT_SCALE;
  return (
    <tr className={isAgent ? "total-row" : undefined}>
      <th scope="row">{strategy.name}</th>
      <td className={returnTone(value) === "flat" ? undefined : returnTone(value)}>{formatSignedPercentTwo(value)}</td>
      <td>{formatPercentTwo(strategy.max_drawdown_pct / PERCENT_SCALE)}</td>
      <td>{formatPercentOne(strategy.average_exposure_pct / PERCENT_SCALE)}</td>
    </tr>
  );
}

function SymbolStats({ symbol, coverage }: { symbol: string; coverage: number }) {
  return (
    <span className="symbol-stats muted">
      For {symbol}, the real price stayed inside the range <strong>{formatPercentOne(coverage)}</strong> of the time (should be 80%).
    </span>
  );
}

function AccuracySentence({ ratio }: { ratio: number | null }) {
  if (ratio === null) return <p className="summary-line">Accuracy vs assuming the price won't move is not available.</p>;
  const comparison = compare(ratio);
  const wording: Record<Comparison, string> = {
    better: "less than",
    same: "about the same amount as",
    worse: "more than",
  };
  return (
    <p className={`summary-line ${COMPARISON_TONE[comparison]}`}>
      On average, the forecast missed the real price by {wording[comparison]} simply assuming the price won't move (
      {formatChange(ratio)}).
    </p>
  );
}
