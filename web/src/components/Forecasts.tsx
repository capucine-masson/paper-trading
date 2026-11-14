import { formatDateTime, formatPercent, formatUsd } from "../format";
import type { ForecastView } from "../types";
import { Empty } from "./Feedback";

export function Forecasts({ forecasts }: { forecasts: ForecastView[] }) {
  return (
    <section className="card">
      <h2>Latest forecasts</h2>
      {forecasts.length === 0 ? (
        <Empty message="No forecast in this view." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Last price</th>
                <th className="num">Median</th>
                <th>10%-90% interval</th>
                <th className="num">Uncertainty</th>
                <th>Model, horizon</th>
              </tr>
            </thead>
            <tbody>
              {forecasts.map((f) => (
                <tr key={f.symbol}>
                  <td>{f.symbol}</td>
                  <td className="num">{formatUsd(f.last_price)}</td>
                  <td className="num">{formatUsd(f.median)}</td>
                  <td>
                    <IntervalBar forecast={f} />
                  </td>
                  <td className="num">{formatPercent(f.uncertainty)}</td>
                  <td className="muted">
                    {f.model}, {f.horizon_steps}h, bar {formatDateTime(f.last_bar_start)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function IntervalBar({ forecast }: { forecast: ForecastView }) {
  const span = Math.max(forecast.upper - forecast.lower, 1e-9);
  const at = (value: number) => `${((value - forecast.lower) / span) * 100}%`;
  return (
    <div className="interval" title={`${formatUsd(forecast.lower)} to ${formatUsd(forecast.upper)}`}>
      <span className="interval-bar" />
      <span className="interval-mark interval-median" style={{ left: at(forecast.median) }} />
      <span className="interval-mark interval-last" style={{ left: at(forecast.last_price) }} />
      <span className="interval-label">
        {formatUsd(forecast.lower)} to {formatUsd(forecast.upper)}
      </span>
    </div>
  );
}
