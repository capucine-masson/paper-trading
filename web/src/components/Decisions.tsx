import type { ReactNode } from "react";
import { forSymbol } from "../filters";
import { expectedMove, formatMacro, rangeWidth } from "../forecast";
import {
  formatDateTime,
  formatPercent,
  formatPercentOne,
  formatShares,
  formatSignedPercent,
  formatUsd,
} from "../format";
import { ALL_SYMBOLS, type DecisionView } from "../types";
import { Empty } from "./Feedback";
import { FanChart } from "./FanChart";

const MAX_CARDS = 30;
const NOT_AVAILABLE = "n/a";

interface Props {
  decisions: DecisionView[];
  symbols: string[];
  symbol: string;
  onSymbol: (symbol: string) => void;
}

export function Decisions({ decisions, symbols, symbol, onSymbol }: Props) {
  const shown = forSymbol(decisions, symbol);
  const cycles = groupByCycle([...shown].reverse());
  const latest = cycles.slice(0, MAX_CARDS);
  const horizon = decisions.find((d) => d.forecast !== null)?.forecast?.median.length ?? 0;
  return (
    <div className="page-section">
      <div className="section-head">
        <h2>Decisions</h2>
        <label className="field">
          Symbol
          <select value={symbol} onChange={(e) => onSymbol(e.target.value)}>
            <option value={ALL_SYMBOLS}>All symbols</option>
            {symbols.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {latest.length === 0 ? (
        <Empty message="No decision in this view." />
      ) : (
        <>
          <div className="card decision-list">
            <div className="decision-columns" aria-hidden="true">
              <span title="The ETF the decision is about.">Symbol</span>
              <span title="What the AI proposes: buy, sell or hold.">Action</span>
              <span title="How much the price is expected to change, according to Timestral.">
                Expected return ({horizon}h)
              </span>
              <span className="col-range" title="How unsure the forecast is: a wider range means less certainty.">
                Uncertainty (80% range)
              </span>
              <span title="Price when the decision was made.">Price</span>
              <span title="What happened: an order was placed, blocked by a rule, or nothing was done.">
                Result
              </span>
            </div>
            {latest.map((cycle, index) => (
              <CycleGroup key={cycle[0].cycle_id} decisions={cycle} defaultOpen={index === 0} />
            ))}
          </div>
          {cycles.length > MAX_CARDS && (
            <p className="muted">
              Showing the latest {MAX_CARDS} of {cycles.length} cycles. The decisions CSV holds all of them.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function groupByCycle(decisions: DecisionView[]): DecisionView[][] {
  const cycles = new Map<string, DecisionView[]>();
  for (const d of decisions) {
    const group = cycles.get(d.cycle_id);
    if (group === undefined) cycles.set(d.cycle_id, [d]);
    else group.push(d);
  }
  return [...cycles.values()];
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** A blocked decision is only a proposal: it gets an orange pill instead of the green or red one. */
const pillClass = (d: DecisionView): string => `pill pill-${d.verdict === "blocked" ? "blocked" : d.action}`;

function CycleGroup({ decisions, defaultOpen }: { decisions: DecisionView[]; defaultOpen: boolean }) {
  const orders = decisions.filter((d) => d.order !== null).length;
  const blocked = decisions.filter((d) => d.verdict === "blocked").length;
  return (
    <details className="cycle-group" open={defaultOpen}>
      <summary className="cycle-summary">
        <time dateTime={decisions[0].t}>{formatDateTime(decisions[0].t)}</time>
        <span className="muted">
          {plural(decisions.length, "decision")} · {plural(orders, "order")} · {blocked} blocked
        </span>
        <span className="cycle-pills">
          {decisions.map((d) => (
            <span key={d.symbol} className={pillClass(d)}>
              {d.symbol} {d.action}
              {d.verdict === "blocked" ? " blocked" : ""}
            </span>
          ))}
        </span>
      </summary>
      {decisions.map((d) => (
        <DecisionRow key={d.symbol} decision={d} />
      ))}
    </details>
  );
}

function DecisionRow({ decision: d }: { decision: DecisionView }) {
  return (
    <details className="decision-row">
      <summary className="decision-summary">
        <strong>{d.symbol}</strong>
        <span>
          <span className={pillClass(d)}>{d.action}</span>
        </span>
        <Expected decision={d} />
        <span className="col-range">{d.forecast === null ? NOT_AVAILABLE : formatPercentOne(rangeWidth(d.forecast))}</span>
        <span>{d.price === null ? NOT_AVAILABLE : formatUsd(d.price)}</span>
        <Result decision={d} />
      </summary>
      <div className="decision-body">
        <div className="decision-chart">
          {d.forecast !== null && d.price !== null && <FanChart forecast={d.forecast} price={d.price} />}
        </div>
        <div className="decision-text">
          <p className="rationale">{d.rationale}</p>
          <DetailLine label="Sizing">{sizing(d)}</DetailLine>
          <DetailLine label="Already owned">
            {d.position_qty === 0 ? "None" : formatUsd(d.position_value)}
          </DetailLine>
          <DetailLine label="Also used">{contextSentence(d)}</DetailLine>
          {d.risk_reason !== null && d.verdict !== "no_order" && (
            <DetailLine label="Risk check">{riskNote(d)}</DetailLine>
          )}
        </div>
      </div>
    </details>
  );
}

function DetailLine({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="outcome">
      <span className="outcome-label">{label}</span>
      <span>{children}</span>
    </div>
  );
}

function riskNote(d: DecisionView): string {
  return d.verdict === "blocked" ? `Blocked: ${d.risk_reason}` : `Approved: ${d.risk_reason}`;
}

function sizing(d: DecisionView): string {
  if (d.forecast === null) return "No forecast.";
  const strength = d.signal_strength === null ? NOT_AVAILABLE : formatPercent(d.signal_strength);
  const range = `Range ${formatPercentOne(rangeWidth(d.forecast))} · signal strength ${strength}`;
  return d.action === "buy" ? `${range} → asks for ${formatPercent(d.size_fraction)} of the maximum position` : range;
}

function contextSentence(d: DecisionView): string {
  const drivers = Object.entries(d.macro).map(([name, value]) => formatMacro(name, value));
  const parts = [
    ...(drivers.length === 0 ? [] : [`Besides the price, Timestral also used: ${drivers.join(", ")}.`]),
    ...(d.next_event === null
      ? []
      : [`Next scheduled event (Fed decision or inflation report): ${formatDateTime(d.next_event)}.`]),
  ];
  return parts.length === 0 ? "No macro data was recorded for this decision." : parts.join(" ");
}

function Expected({ decision: d }: { decision: DecisionView }) {
  if (d.forecast === null || d.price === null) return <span className="muted">{NOT_AVAILABLE}</span>;
  const move = expectedMove(d.forecast, d.price);
  return <span className={move === 0 ? undefined : move > 0 ? "up" : "down"}>{formatSignedPercent(move)}</span>;
}

function Result({ decision: d }: { decision: DecisionView }) {
  if (d.order !== null) {
    const { side, qty, fill_price: fill, status } = d.order;
    const filled = qty !== null && qty > 0 && fill !== null;
    const label = !filled ? "Pending" : side === "buy" ? "Bought" : "Sold";
    const detail = filled
      ? `${formatUsd(qty * fill)} · ${formatShares(qty)} sh @ ${formatUsd(fill)}`
      : `order ${status}`;
    return (
      <span className="result">
        <span className={`verdict verdict-${d.verdict}`} title={d.risk_reason ?? undefined}>
          {label}
        </span>{" "}
        {detail}
      </span>
    );
  }
  if (d.verdict === "blocked") {
    return (
      <span className="result" title={d.risk_reason ?? undefined}>
        <span className="verdict verdict-blocked">Blocked</span> <span className="muted">{d.risk_reason}</span>
      </span>
    );
  }
  return <span className="result muted">No trade</span>;
}
