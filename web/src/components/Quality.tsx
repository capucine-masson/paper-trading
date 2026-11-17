import { formatDate, formatPercentOne, formatPercentTwo, formatSignedPercentTwo } from "../format";
import { forSymbol } from "../filters";
import type { BacktestReport, StrategyResult } from "../types";
import { Empty } from "./Feedback";
import { Flower } from "./Flower";
import { ForecastFan } from "./ForecastFan";

const TARGET_COVERAGE = 0.8;
const COVERAGE_TOLERANCE = 0.05;
const NAIVE_RATIO = 1;
const SAME_TOLERANCE = 0.02;
const BAR_UNIT = "hours";
const FAN_FORECASTS = 120;
const FAN_DEFAULT_SYMBOL = "SPY";
const PERCENT_SCALE = 100;
const COLUMN_HINTS = {
  strategy: "A way of deciding what to buy or sell, replayed on the same past period.",
  return: "How much money the strategy made or lost over the period.",
  drawdown: "The worst drop from a previous high point. Smaller is safer.",
  exposure: "Share of the portfolio invested on average. The rest stayed in cash.",
} as const;

const STRATEGY_HINTS: Record<string, string> = {
  "Equal-weight buy and hold": "Buys every symbol in equal parts at the start and never trades again.",
  "Timestral-only rule": "Follows the Timestral forecast alone: buys when it expects a rise, sells otherwise.",
  "Buy and hold (same exposure as agent)": "Holds the same amount of risk as the agent, without any forecast.",
  "Timestral + LLM (the agent)": "Our agent: the forecast, then the AI decision, then the risk rules.",
};

type Tone = "up" | "flat" | "down";
type Comparison = "better" | "same" | "worse";

const COMPARISON_TONE: Record<Comparison, Tone> = { better: "up", same: "flat", worse: "down" };

const hitRateTone = (coverage: number): Tone =>
  Math.abs(coverage - TARGET_COVERAGE) <= COVERAGE_TOLERANCE ? "up" : "down";

const ERROR_VERDICT: Record<Comparison, string> = {
  better: "Better than no-move",
  same: "Same as no-move",
  worse: "Worse than no-move",
};

const coverageVerdict = (coverage: number): string =>
  hitRateTone(coverage) === "up" ? "Well sized" : coverage < TARGET_COVERAGE ? "Overconfident" : "Underconfident";

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
      <div className="quality-body">
        <div className="quality-side">
          <div className="quality-intro">
            <h3>Can we trust the forecasts?</h3>
            <p>
              We replayed the past: the model forecast prices using only earlier data, and we compared each forecast
              with what really happened.
            </p>
            <p className="muted quality-meta">
              {model.overall.n.toLocaleString("en-US")} forecasts, each {backtest.horizon_bars} {BAR_UNIT} ahead
              <br />
              {formatDate(backtest.decision_start)} to {formatDate(backtest.history_end)}, after the model's release
              (no look-ahead)
              <br />
              {model.model} · run on {formatDate(backtest.generated_at)}
            </p>
          </div>
          <section className="card quality-summary">
            <Metric
              value={formatPercentOne(coverage)}
              label="Price inside forecast range"
              verdict={`${coverageVerdict(coverage)} (target ${TARGET_COVERAGE * PERCENT_SCALE}%)`}
              tone={hitRateTone(coverage) === "up" ? "flat" : "down"}
            />
            {ratio !== null && (
              <Metric
                value={formatChange(ratio)}
                label="Error vs a no-move guess"
                verdict={ERROR_VERDICT[compare(ratio)]}
                tone={COMPARISON_TONE[compare(ratio)]}
              />
            )}
            {direction !== null && (
              <Metric
                value={formatPercentOne(direction)}
                label="Direction guessed right"
                verdict="Almost random"
                tone="flat"
              />
            )}
          </section>
          <section className="card quality-details">
            <table className="quality-table">
              <thead>
                <tr>
                  <th scope="col" title={COLUMN_HINTS.strategy}>
                    Strategy
                  </th>
                  <th scope="col" title={COLUMN_HINTS.return}>
                    Return
                  </th>
                  <th scope="col" title={COLUMN_HINTS.drawdown}>
                    Max drawdown
                  </th>
                  <th scope="col" title={COLUMN_HINTS.exposure}>
                    Avg exposure
                  </th>
                </tr>
              </thead>
              <tbody>
                {backtest.strategies.map((strategy) => (
                  <StrategyRow key={strategy.name} strategy={strategy} />
                ))}
              </tbody>
            </table>
            <p className="muted quality-note">
              All strategies follow the same rules and costs. The gaps are too small to prove anything.
              <br />
              The Overview chart shows live paper trading, a different and shorter period.
            </p>
          </section>
        </div>
        <section className="card quality-chart">
          <Flower />
          <div className="section-head">
            <h3>Timestral forecast vs real price</h3>
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
  const value = strategy.return_pct / PERCENT_SCALE;
  return (
    <tr>
      <th scope="row" title={STRATEGY_HINTS[strategy.name]}>
        {strategy.name}
      </th>
      <td className={returnTone(value) === "flat" ? undefined : returnTone(value)}>{formatSignedPercentTwo(value)}</td>
      <td>{formatPercentTwo(strategy.max_drawdown_pct / PERCENT_SCALE)}</td>
      <td>{formatPercentOne(strategy.average_exposure_pct / PERCENT_SCALE)}</td>
    </tr>
  );
}

function SymbolStats({ symbol, coverage }: { symbol: string; coverage: number }) {
  return (
    <span className="symbol-stats muted">
      <span>For {symbol}, the real price stayed inside the range</span>
      <span>
        <strong>{formatPercentOne(coverage)}</strong> of the time (should be 80%).
      </span>
    </span>
  );
}

interface MetricProps {
  value: string;
  label: string;
  verdict: string;
  tone: Tone;
}

function Metric({ value, label, verdict, tone }: MetricProps) {
  return (
    <div className="metric">
      <span className={`metric-value ${tone}`}>{value}</span>
      <span className="metric-label">{label}</span>
      <span className={`metric-verdict ${tone}`}>{verdict}</span>
    </div>
  );
}
