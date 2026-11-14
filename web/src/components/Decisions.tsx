import { formatDateTime, formatPercent } from "../format";
import type { DecisionView } from "../types";
import { Empty } from "./Feedback";

const MAX_ROWS = 25;

export function Decisions({ decisions }: { decisions: DecisionView[] }) {
  const latest = [...decisions].reverse().slice(0, MAX_ROWS);
  return (
    <section className="card">
      <h2>Latest decisions</h2>
      {latest.length === 0 ? (
        <Empty message="No decision in this view." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>LLM</th>
                <th>Rationale</th>
                <th>Risk verdict</th>
                <th>Order</th>
              </tr>
            </thead>
            <tbody>
              {latest.map((d) => (
                <tr key={`${d.cycle_id}-${d.symbol}`}>
                  <td className="nowrap">{formatDateTime(d.t)}</td>
                  <td>{d.symbol}</td>
                  <td className="nowrap">
                    <span className={`pill pill-${d.action}`}>{d.action}</span>{" "}
                    {formatPercent(d.confidence)}
                  </td>
                  <td>{d.rationale}</td>
                  <td>
                    {d.approved === null ? "n/a" : d.approved ? "Approved" : "Rejected"}
                    {d.risk_reason ? `: ${d.risk_reason}` : ""}
                  </td>
                  <td className="nowrap">{d.order_status ?? "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
