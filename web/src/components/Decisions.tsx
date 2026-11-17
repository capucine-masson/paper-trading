import { Fragment, useState, type ReactNode } from "react";
import { forSymbol } from "../filters";
import { expectedMove, formatMacro, rangeWidth } from "../forecast";
import {
  formatDateTime,
  formatDay,
  formatPercent,
  formatPercentOne,
  formatShares,
  formatSignedPercent,
  formatTime,
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
  const [openCycle, setOpenCycle] = useState<string | null>(null);
  return (
    <div className="page-section">
      <div className="card decision-list">
        <div className={`decision-columns${openCycle === null ? " is-collapsed" : ""}`}>
          <select
            aria-label="Symbol"
            title="The ETF the decision is about."
            value={symbol}
            onChange={(e) => onSymbol(e.target.value)}
          >
            <option value={ALL_SYMBOLS}>All symbols</option>
            {symbols.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <span aria-hidden="true" title="What the AI proposes: buy, sell or hold.">Action</span>
          <span aria-hidden="true" title="Price when the decision was made.">Price</span>
          <span aria-hidden="true" title="What happened: an order was placed, blocked by a rule, or nothing was done.">
            Result
          </span>
        </div>
        {latest.length === 0 ? (
          <Empty message="No decision in this view." />
        ) : (
          <>
            {latest.map((cycle, index) => (
              <Fragment key={cycle[0].cycle_id}>
                {(index === 0 || formatDay(latest[index - 1][0].t) !== formatDay(cycle[0].t)) && (
                  <div className="day-label">{formatDay(cycle[0].t)}</div>
                )}
                <CycleGroup
                  decisions={cycle}
                  open={cycle[0].cycle_id === openCycle}
                  onToggle={(isOpen) =>
                    setOpenCycle((current) => (isOpen ? cycle[0].cycle_id : current === cycle[0].cycle_id ? null : current))
                  }
                />
              </Fragment>
            ))}
          </>
        )}
      </div>
      {cycles.length > MAX_CARDS && (
        <p className="muted">
          Showing the latest {MAX_CARDS} of {cycles.length} cycles. The decisions CSV holds all of them.
        </p>
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

interface CycleGroupProps {
  decisions: DecisionView[];
  open: boolean;
  onToggle: (isOpen: boolean) => void;
}

function CycleGroup({ decisions, open, onToggle }: CycleGroupProps) {
  const [openSymbol, setOpenSymbol] = useState<string | null>(null);
  const events = decisions.filter(hasEvent);
  const quiet = decisions.filter((d) => !hasEvent(d));
  const orders = decisions.filter((d) => d.order !== null).length;
  const blocked = decisions.filter((d) => d.verdict === "blocked").length;
  const renderRow = (d: DecisionView): ReactNode => (
    <DecisionRow
      key={d.symbol}
      decision={d}
      open={d.symbol === openSymbol}
      onToggle={(isOpen) => setOpenSymbol((current) => (isOpen ? d.symbol : current === d.symbol ? null : current))}
    />
  );
  return (
    <details className="cycle-group" open={open} onToggle={(e) => onToggle(e.currentTarget.open)}>
      <summary className="cycle-summary">
        <time dateTime={decisions[0].t}>{formatTime(decisions[0].t)}</time>
        <span className="muted">
          {orders === 0 && blocked === 0 ? "Hold" : `${plural(orders, "order")} · ${blocked} blocked`}
        </span>
        <span className="cycle-pills">
          {events.map((d) => (
            <span key={d.symbol} className={pillClass(d)} title={`${d.symbol} ${d.action}${d.verdict === "blocked" ? " blocked" : ""}`}>
              {d.symbol} {d.verdict === "blocked" ? "blocked" : d.action}
            </span>
          ))}
          {quiet.length > 0 && (
            <span className="muted cycle-quiet">
              {events.length > 0 ? `+${quiet.length}` : quiet.length} no trade
            </span>
          )}
        </span>
      </summary>
      {events.map(renderRow)}
      {quiet.length > 0 && <QuietRows decisions={quiet} openByDefault={events.length === 0} renderRow={renderRow} />}
    </details>
  );
}

const hasEvent = (d: DecisionView): boolean => d.order !== null || d.verdict === "blocked";

interface QuietRowsProps {
  decisions: DecisionView[];
  openByDefault: boolean;
  renderRow: (d: DecisionView) => ReactNode;
}

function QuietRows({ decisions, openByDefault, renderRow }: QuietRowsProps) {
  const [open, setOpen] = useState(openByDefault);
  return (
    <details className="decision-row" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="decision-summary quiet-summary">
        <span className="muted">{plural(decisions.length, "symbol")} with no trade</span>
        <span className="muted quiet-symbols">{decisions.map((d) => d.symbol).join(" · ")}</span>
      </summary>
      {decisions.map(renderRow)}
    </details>
  );
}

interface DecisionRowProps {
  decision: DecisionView;
  open: boolean;
  onToggle: (isOpen: boolean) => void;
}

function DecisionRow({ decision: d, open, onToggle }: DecisionRowProps) {
  return (
    <details className="decision-row" open={open} onToggle={(e) => onToggle(e.currentTarget.open)}>
      <summary className="decision-summary">
        <strong>{d.symbol}</strong>
        <span>
          <span className={pillClass(d)}>{d.action}</span>
        </span>
        <span>{d.price === null ? NOT_AVAILABLE : formatUsd(d.price)}</span>
        <Result decision={d} />
      </summary>
      <div className="decision-body">
        <div className="decision-chart">
          {d.forecast !== null && d.price !== null && (
            <FanChart forecast={d.forecast} price={d.price} />
          )}
          <TimestralInputs decision={d} />
        </div>
        <div className="decision-text">
          <p className="rationale">{d.rationale}</p>
          {d.forecast !== null && (
            <>
              <DetailLine label={`Expected move (${d.forecast.median.length}h)`} hint={HINTS.expectedMove}>
                <Expected decision={d} />
              </DetailLine>
              <DetailLine label="Signal strength" hint={HINTS.signal}>
                {d.signal_strength === null ? NOT_AVAILABLE : formatPercent(d.signal_strength)}
              </DetailLine>
              <DetailLine label="Range (80%)" hint={HINTS.range}>
                {formatPercentOne(rangeWidth(d.forecast))}
              </DetailLine>
            </>
          )}
          <DetailLine label="Sizing" hint={HINTS.sizing}>{sizing(d)}</DetailLine>
          <DetailLine label="Already owned" hint={HINTS.owned}>
            {d.position_qty === 0 ? "None" : formatUsd(d.position_value)}
          </DetailLine>
          {d.risk_reason !== null && d.verdict !== "no_order" && (
            <DetailLine label="Risk check" hint={HINTS.risk}>{riskNote(d)}</DetailLine>
          )}
        </div>
      </div>
    </details>
  );
}

const PENDING_HINT = "The order was sent to the broker but is not filled yet. It is updated at the next cycle.";
const FAILED_ORDERS: Readonly<Record<string, string>> = { canceled: "Canceled", expired: "Expired", rejected: "Rejected" };

const HINTS = {
  expectedMove: "How much Timestral thinks the price will move over this period.",
  signal: "How clear the forecast is, from 0% (nothing clear) to 100% (very clear). Computed by our code from the Timestral forecast.",
  range: "The gap between a good and a bad scenario. The wider it is, the less sure Timestral is.",
  sizing: "How big a trade the LLM asks for.",
  owned: "What we already hold of this ETF.",
  market: "Oil, interest rates and market fear, given to Timestral as context.",
  release: "Whether a Fed or inflation announcement falls in this period. Timestral is told in advance.",
  risk: "Our safety rules. They can block a trade the LLM proposed.",
} as const;

function DetailLine({ label, hint, children }: { label: string; hint: string; children: ReactNode }) {
  return (
    <div className="outcome">
      <span className="outcome-label">
        <span className="hint" tabIndex={0}>
          {label}
          <span className="hint-icon" aria-hidden="true">
            i
          </span>
          <span className="hint-tip" role="tooltip">
            {hint}
          </span>
        </span>
      </span>
      <span>{children}</span>
    </div>
  );
}

function riskNote(d: DecisionView): string {
  return d.verdict === "blocked" ? `Blocked: ${d.risk_reason}` : `Approved: ${d.risk_reason}`;
}

function sizing(d: DecisionView): string {
  if (d.action === "hold") return "No order";
  const asked = `LLM asks ${formatPercent(d.size_fraction)} of the ${d.action === "buy" ? "maximum " : ""}position`;
  const amount = d.order?.notional ?? null;
  return amount === null ? asked : `${asked} → order ${formatUsd(amount)}`;
}

function TimestralInputs({ decision: d }: { decision: DecisionView }) {
  const market = Object.entries(d.macro).map(([name, value]) => formatMacro(name, value));
  if (d.forecast === null || (market.length === 0 && d.next_event === null)) return null;
  const upcoming = d.next_event === null ? "" : formatDateTime(d.next_event);
  return (
    <>
      <DetailLine label="Market data" hint={HINTS.market}>
        {market.map(({ label, value }) => `${label} ${value}`).join(" · ")}
      </DetailLine>
      <DetailLine label={`Release in ${d.forecast.median.length}h`} hint={HINTS.release}>
        {d.event_in_horizon ? `Yes, ${upcoming}` : `No${upcoming === "" ? "" : `, next one ${upcoming}`}`}
      </DetailLine>
    </>
  );
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
    const failure = FAILED_ORDERS[status];
    const waiting = !filled && failure === undefined;
    const label = filled ? (side === "buy" ? "Bought" : "Sold") : (failure ?? "Pending");
    const detail = filled
      ? `${formatShares(qty)} ${qty === 1 ? "share" : "shares"} at ${formatUsd(fill)} → ${formatUsd(qty * fill)}`
      : waiting
        ? "Waiting to be filled"
        : "The order was not executed";
    const verdict = failure === undefined ? d.verdict : "blocked";
    const title = waiting ? PENDING_HINT : d.risk_reason;
    return (
      <span className="result">
        <span className={`verdict verdict-${verdict}`} title={title ?? undefined}>
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
