import { formatUsd } from "../format";
import { ALL_SYMBOLS, type EquityPoint, type PositionView } from "../types";
import { Empty } from "./Feedback";
import { LineChart } from "./LineChart";

interface Props {
  points: EquityPoint[];
  positions: PositionView[];
  symbol: string;
}

export function Portfolio({ points, positions, symbol }: Props) {
  const bySymbol = symbol !== ALL_SYMBOLS;
  const series = points.map((p) => ({
    t: p.t,
    value: bySymbol ? (p.positions[symbol] ?? 0) : p.equity,
  }));
  return (
    <section className="card">
      <h2>{bySymbol ? `${symbol} position value` : "Portfolio value"}</h2>
      <LineChart
        points={series}
        formatValue={formatUsd}
        label={bySymbol ? `${symbol} position value over time` : "Portfolio value over time"}
      />
      <h3>Positions</h3>
      {positions.length === 0 ? (
        <Empty message="No open position." />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="num">Quantity</th>
              <th className="num">Market value</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol}</td>
                <td className="num">{p.qty}</td>
                <td className="num">{formatUsd(p.market_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
