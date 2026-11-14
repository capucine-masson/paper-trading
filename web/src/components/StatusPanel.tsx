import { formatDateTime, formatUsd } from "../format";
import type { Status } from "../types";

export function StatusPanel({ status }: { status: Status }) {
  const cycle = status.last_cycle;
  return (
    <section className="card">
      <h2>Status</h2>
      <div className="metrics">
        <Metric label="Equity" value={status.equity === null ? "n/a" : formatUsd(status.equity)} />
        <Metric
          label="PnL"
          value={status.pnl === null ? "n/a" : formatUsd(status.pnl)}
          tone={status.pnl === null ? undefined : status.pnl >= 0 ? "up" : "down"}
        />
        <Metric label="Allocated capital" value={formatUsd(status.allocated_capital)} />
      </div>
      {status.halted_reason !== null && (
        <p className="notice notice-halted">
          Halted: {status.halted_reason}. Orders are blocked until a manual resume.
        </p>
      )}
      {status.state === "stopped" && (
        <p className="notice notice-halted">Emergency stop is on: every order is blocked.</p>
      )}
      {cycle === null ? (
        <p className="muted">No cycle has run yet.</p>
      ) : (
        <p className="muted">
          Last cycle {cycle.cycle_id} started {formatDateTime(cycle.started_at)}:{" "}
          <strong className={cycle.status === "error" ? "down" : undefined}>
            {cycle.status ?? "running"}
          </strong>
          {cycle.detail ? ` (${cycle.detail})` : ""}
        </p>
      )}
      <p className="muted">Data exported {formatDateTime(status.generated_at)}</p>
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="metric">
      <span className="muted">{label}</span>
      <span className={`metric-value ${tone ?? ""}`}>{value}</span>
    </div>
  );
}
