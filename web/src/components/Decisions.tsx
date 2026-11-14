import { forSymbol } from "../filters";
import { formatDateTime, formatPercent, formatUsd } from "../format";
import { ALL_SYMBOLS, type DecisionView, type TradeView, type VerdictStatus } from "../types";
import { Empty } from "./Feedback";
import { FanChart } from "./FanChart";

const MAX_CARDS = 30;
const VERDICT_LABEL: Record<VerdictStatus, string> = {
  accepted: "Accepted",
  reduced: "Reduced",
  blocked: "Blocked",
  no_order: "No order",
};

interface Props {
  decisions: DecisionView[];
  symbols: string[];
  symbol: string;
  onSymbol: (symbol: string) => void;
}

export function Decisions({ decisions, symbols, symbol, onSymbol }: Props) {
  const shown = forSymbol(decisions, symbol);
  const latest = [...shown].reverse().slice(0, MAX_CARDS);
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
              <span>Time</span>
              <span>Symbol</span>
              <span>Action</span>
              <span>Confidence</span>
              <span>Price</span>
              <span>Guardrails</span>
              <span>Order</span>
            </div>
            {latest.map((d) => (
              <DecisionRow key={`${d.cycle_id}-${d.symbol}`} decision={d} />
            ))}
          </div>
          {shown.length > MAX_CARDS && (
            <p className="muted">
              Showing the latest {MAX_CARDS} of {shown.length} decisions. The decisions CSV holds all of them.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function DecisionRow({ decision: d }: { decision: DecisionView }) {
  return (
    <details className="decision-row">
      <summary className="decision-summary">
        <time dateTime={d.t}>{formatDateTime(d.t)}</time>
        <strong>{d.symbol}</strong>
        <span>
          <span className={`pill pill-${d.action}`}>{d.action}</span>
        </span>
        <span>{formatPercent(d.confidence)}</span>
        <span className="num">{d.price === null ? "n/a" : formatUsd(d.price)}</span>
        <span>
          <span className={`verdict verdict-${d.verdict}`}>{VERDICT_LABEL[d.verdict]}</span>
        </span>
        <Order order={d.order} />
      </summary>
      <div className="decision-body">
        <div className="decision-chart">
          <dl className="facts">
            <div>
              <dt>Price</dt>
              <dd>{d.price === null ? "n/a" : formatUsd(d.price)}</dd>
            </div>
            <div>
              <dt>Position before</dt>
              <dd>{d.position_qty === 0 ? "None" : `${d.position_qty} sh, ${formatUsd(d.position_value)}`}</dd>
            </div>
          </dl>
          {d.forecast !== null && d.price !== null && <FanChart forecast={d.forecast} price={d.price} />}
        </div>
        <div className="decision-text">
          <p className="rationale">{d.rationale}</p>
          <div className="outcome">
            <span className="outcome-label">Guardrails</span>
            <span className={`verdict verdict-${d.verdict}`}>{VERDICT_LABEL[d.verdict]}</span>
            {d.risk_reason !== null && <span className="muted">{d.risk_reason}</span>}
          </div>
          <div className="outcome">
            <span className="outcome-label">Alpaca order</span>
            <Order order={d.order} />
          </div>
        </div>
      </div>
    </details>
  );
}

function Order({ order }: { order: TradeView | null }) {
  if (order === null) return <span className="muted">No order sent</span>;
  const quantity = order.qty === null ? "" : ` ${order.qty}`;
  const fill = order.fill_price === null ? "fill pending" : `filled at ${formatUsd(order.fill_price)}`;
  return (
    <span>
      <strong className="upper">{order.side}</strong>
      {quantity}{" "}
      <span className="muted">
        {order.status}, {fill}
      </span>
    </span>
  );
}
