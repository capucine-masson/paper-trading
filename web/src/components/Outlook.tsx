import { expectedMove, latestForecasts, rangeWidth } from "../forecast";
import { formatPercentOne, formatSignedPercent, formatUsd } from "../format";
import type { DecisionView } from "../types";

const FORECAST_STEP_HOURS = 1;

export function Outlook({ decisions, symbols }: { decisions: DecisionView[]; symbols: string[] }) {
  const latest = latestForecasts(decisions);
  const first = symbols.map((symbol) => latest.get(symbol)).find((d) => d !== undefined);
  const horizon = (first?.forecast?.median.length ?? 0) * FORECAST_STEP_HOURS;
  return (
    <section className="card outlook-card">
      <div className="card-head">
        <h2>Outlook</h2>
        <span className="muted">
          {first === undefined
            ? "No forecast yet"
            : `Latest forecast, next ${horizon}h`}
        </span>
      </div>
      <table className="outlook">
        <thead>
          <tr>
            <th scope="col" />
            {symbols.map((symbol) => (
              <th key={symbol} scope="col">
                {symbol}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Expected move</th>
            {symbols.map((symbol) => (
              <OutlookCell key={symbol} decision={latest.get(symbol)} kind="move" />
            ))}
          </tr>
          <tr>
            <th scope="row">80% range width</th>
            {symbols.map((symbol) => (
              <OutlookCell key={symbol} decision={latest.get(symbol)} kind="width" />
            ))}
          </tr>
        </tbody>
      </table>
    </section>
  );
}

function OutlookCell({ decision, kind }: { decision: DecisionView | undefined; kind: "move" | "width" }) {
  if (decision === undefined || decision.forecast === null || decision.price === null) {
    return <td className="muted">n/a</td>;
  }
  const { forecast, price } = decision;
  const last = forecast.median.length - 1;
  const range = `${formatUsd(forecast.lower[last] ?? price)} to ${formatUsd(forecast.upper[last] ?? price)}`;
  if (kind === "width") return <td title={range}>{formatPercentOne(rangeWidth(forecast))}</td>;
  const move = expectedMove(forecast, price);
  return <td className={move === 0 ? undefined : move > 0 ? "up" : "down"}>{formatSignedPercent(move)}</td>;
}
