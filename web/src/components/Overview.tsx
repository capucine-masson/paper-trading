import { useMemo } from "react";
import { EXPORT_LINKS, exportUrl } from "../api";
import { forSymbol, inPeriod } from "../filters";
import {
  formatDateTime,
  formatDrawdown,
  formatPercent,
  formatSignedPercent,
  formatSignedUsd,
  formatUsd,
} from "../format";
import { ALL_SYMBOLS, type DecisionView, type Metrics, type Period, type PortfolioData, type PositionView, type Status } from "../types";
import { EquityChart, type OrderMark } from "./EquityChart";
import { Outlook } from "./Outlook";

const PERIOD_LABELS: { value: Period; label: string }[] = [
  { value: "1d", label: "1D" },
  { value: "3d", label: "3D" },
  { value: "all", label: "All" },
];
const NOT_AVAILABLE = "n/a";

type Tone = "up" | "down" | undefined;

interface Props {
  status: Status;
  portfolio: PortfolioData;
  decisions: DecisionView[];
  symbol: string;
  period: Period;
  onSymbol: (symbol: string) => void;
  onPeriod: (period: Period) => void;
}

export function Overview({ status, portfolio, decisions, symbol, period, onSymbol, onPeriod }: Props) {
  const points = inPeriod(portfolio.points, period, status.generated_at);
  const orders = useMemo(() => ordersByCycle(forSymbol(decisions, symbol)), [decisions, symbol]);
  const isAll = symbol === ALL_SYMBOLS;
  return (
    <div className="overview">
      <aside className="side">
        <Performance metrics={status.metrics} />
        <Allocation metrics={status.metrics} />
        <Positions positions={portfolio.positions} />
      </aside>
      <section className="card chart-card">
        <div className="card-head">
          <h2>{isAll ? "Portfolio value" : `${symbol} price`}</h2>
          <span className="legend">
            {isAll && (
              <>
                <i className="swatch swatch-equity" /> Agent
                <i className="swatch swatch-reference" /> Buy &amp; hold (same exposure)
              </>
            )}
            <i className="dot dot-buy" /> Buy
            <i className="dot dot-sell" /> Sell
            {isAll && (
              <>
                <i className="dot dot-mixed" /> Buy and sell
              </>
            )}
          </span>
          <label className="field">
            Symbol
            <select value={symbol} onChange={(e) => onSymbol(e.target.value)}>
              <option value={ALL_SYMBOLS}>All symbols</option>
              {status.symbols.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <div className="segmented" role="group" aria-label="Period">
            {PERIOD_LABELS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={option.value === period}
                onClick={() => onPeriod(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <EquityChart
          points={points}
          symbol={symbol}
          startValue={status.allocated_capital}
          capitalFloor={status.capital_floor}
          orders={orders}
        />
      </section>
      <Outlook decisions={decisions} symbols={status.symbols} />
      <footer className="overview-footer">
        <p className="footnote">
          The agent manages {formatUsd(status.allocated_capital)}
          {status.account_size === null
            ? " of its Alpaca paper account."
            : ` of a ${formatUsd(status.account_size)} Alpaca paper account.`}{" "}
          Paper trading only, not investment advice.
        </p>
        <RunInfo status={status} />
        <ExportBar />
      </footer>
    </div>
  );
}

function ordersByCycle(decisions: DecisionView[]): Map<string, OrderMark[]> {
  const orders = new Map<string, OrderMark[]>();
  for (const d of decisions) {
    if (d.order === null) continue;
    const mark: OrderMark = {
      symbol: d.symbol,
      action: d.order.side,
      price: d.order.fill_price ?? d.price,
      qty: d.order.qty,
    };
    orders.set(d.cycle_id, [...(orders.get(d.cycle_id) ?? []), mark]);
  }
  return orders;
}

function tone(value: number | null): Tone {
  if (value === null || value === 0) return undefined;
  return value > 0 ? "up" : "down";
}

function Performance({ metrics }: { metrics: Metrics }) {
  const { equity, pnl, total_return: ret, buy_and_hold_return: reference, max_drawdown: dd, estimated_costs: costs } = metrics;
  return (
    <div className="card kpis kpis-grid">
      <Kpi
        label="PnL"
        value={pnl === null ? NOT_AVAILABLE : formatSignedUsd(pnl)}
        tone={tone(pnl)}
        sub={equity === null ? undefined : `Equity ${formatUsd(equity)}`}
      />
      <Kpi
        label="Return"
        value={ret === null ? NOT_AVAILABLE : formatSignedPercent(ret)}
        tone={tone(ret)}
        sub={reference === null ? undefined : `Buy & hold ${formatSignedPercent(reference)}`}
      />
      <Kpi
        label="Max drawdown"
        value={dd === null ? NOT_AVAILABLE : formatDrawdown(dd)}
        tone={tone(dd === null ? null : -dd)}
      />
      <Kpi
        label="Est. costs"
        value={costs === null ? NOT_AVAILABLE : formatUsd(costs)}
        sub="Simulated fees"
      />
    </div>
  );
}

function Allocation({ metrics }: { metrics: Metrics }) {
  const { equity, exposure, cash } = metrics;
  if (equity === null || exposure === null || cash === null) {
    return (
      <div className="card allocation">
        <span className="kpi-label">Allocation</span>
        <span className="muted">{NOT_AVAILABLE}</span>
      </div>
    );
  }
  const invested = exposure / equity;
  return (
    <div className="card allocation">
      <span className="kpi-label">Allocation</span>
      <span className="meter meter-large" title={`Invested ${formatUsd(exposure)}, cash ${formatUsd(cash)}`}>
        <span className="meter-fill" style={{ width: `${Math.min(invested, 1) * 100}%` }} />
      </span>
      <div className="allocation-legend">
        <span>
          {formatPercent(invested)} invested <span className="muted">{formatUsd(exposure)}</span>
        </span>
        <span>
          {formatPercent(cash / equity)} cash <span className="muted">{formatUsd(cash)}</span>
        </span>
      </div>
    </div>
  );
}

interface KpiProps {
  label: string;
  value: string;
  sub?: string | undefined;
  tone?: Tone;
}

function Kpi({ label, value, sub, tone: valueTone }: KpiProps) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className={`kpi-value ${valueTone ?? ""}`}>{value}</span>
      <span className="kpi-sub">{sub}</span>
    </div>
  );
}

function Positions({ positions }: { positions: PositionView[] }) {
  const rows = positions.filter((p) => p.qty > 0);
  return (
    <section className="card positions-card">
      <div className="card-head">
        <h2>Positions</h2>
      </div>
      {rows.length === 0 && <p className="muted">No open position.</p>}
      <ul className="positions">
        {rows.map((p) => (
          <li key={p.symbol}>
            <div className="position-row">
              <strong>{p.symbol}</strong>
              <span className="num">{formatUsd(p.market_value)}</span>
              <span className="num muted">{formatPercent(p.weight)}</span>
            </div>
            <span className="meter">
              <span className="meter-fill" style={{ width: `${Math.min(p.weight, 1) * 100}%` }} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RunInfo({ status }: { status: Status }) {
  const cycle = status.last_cycle;
  return (
    <span className="run-info">
      {status.halted_reason !== null && (
        <span className="down">Halted: {status.halted_reason}. Orders are blocked until a manual resume. </span>
      )}
      {status.state === "stopped" && <span className="down">Emergency stop: every order is blocked. </span>}
      {cycle === null ? (
        "No run yet"
      ) : (
        <>
          Last run {formatDateTime(cycle.started_at)}{" "}
          <span className={cycle.status === "error" ? "down" : undefined}>{cycle.status ?? "running"}</span>
        </>
      )}
    </span>
  );
}

function ExportBar() {
  return (
    <div className="links">
      <span className="muted">Export</span>
      {EXPORT_LINKS.map((link) => (
        <a key={link.file} href={exportUrl(link.file)} download>
          {link.label}
        </a>
      ))}
    </div>
  );
}
