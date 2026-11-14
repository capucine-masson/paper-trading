import type {
  BacktestReport,
  DashboardData,
  DecisionView,
  EquityPoint,
  ForecastMetrics,
  VerdictStatus,
} from "./types";

// Development-only sample data to preview the layout (open /?demo=1). Never bundled in production.
const SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GLD"];
const BASE_PRICES: Record<string, number> = { SPY: 750, QQQ: 675, AAPL: 355, MSFT: 524, GLD: 355 };
const CYCLES = 18;
const HORIZON = 6;
const HOUR_MS = 3_600_000;
const ALLOCATED = 10_000;
const ACTIONS: DecisionView["action"][] = ["hold", "buy", "hold", "sell", "hold"];
const VERDICTS: VerdictStatus[] = ["no_order", "accepted", "no_order", "blocked", "no_order"];

const stats = (mae_ratio: number, coverage: number): ForecastMetrics => ({ n: 221, mae_ratio, coverage });

const BACKTEST: BacktestReport = {
  horizon_bars: HORIZON,
  history_start: "2026-05-18T12:00:00Z",
  history_end: "2026-11-13T21:00:00Z",
  models: [
    {
      label: "Main model, all points",
      model: "mistralai/Timestral-28M",
      overall: { n: 1108, mae_ratio: 1.0006, coverage: 0.788 },
      per_symbol: {
        SPY: stats(0.998, 0.77),
        QQQ: stats(1.004, 0.79),
        AAPL: stats(1.003, 0.801),
        MSFT: stats(0.996, 0.8),
        GLD: stats(1.0096, 0.786),
      },
    },
  ],
};

export function buildDemoData(): DashboardData {
  const end = Date.now();
  const iso = (i: number) => new Date(end - (CYCLES - 1 - i) * HOUR_MS).toISOString();
  const points: EquityPoint[] = [];
  const decisions: DecisionView[] = [];
  for (let i = 0; i < CYCLES; i++) {
    const equity = ALLOCATED + 120 * Math.sin(i / 3) + i * 9;
    const spy = ALLOCATED * (1 + 0.0006 * i + 0.004 * Math.sin(i / 2));
    points.push({
      t: iso(i),
      cycle_id: `demo-${i}`,
      equity,
      buy_and_hold: spy,
      exposure: 1_500 + 80 * i,
      positions: { SPY: 900 + 20 * i, AAPL: 600 + 10 * i },
      prices: Object.fromEntries(
        SYMBOLS.map((symbol, s) => [symbol, (BASE_PRICES[symbol] ?? 100) * (1 + 0.002 * Math.sin(i / 2 + s))]),
      ),
    });
    SYMBOLS.forEach((symbol, s) => {
      const last = (BASE_PRICES[symbol] ?? 100) * (1 + 0.002 * Math.sin(i / 2 + s));
      const spread = last * (0.004 + 0.001 * s);
      const drift = last * 0.0004 * (s - 2);
      const steps = Array.from({ length: HORIZON }, (_, k) => k + 1);
      const action = ACTIONS[(i + s) % ACTIONS.length] ?? "hold";
      const verdict = VERDICTS[(i + s) % VERDICTS.length] ?? "no_order";
      const reduced = verdict === "accepted" && i % 4 === 0;
      decisions.push({
        t: iso(i),
        cycle_id: `demo-${i}`,
        symbol,
        action,
        confidence: 0.6 + 0.05 * ((i + s) % 6),
        rationale:
          "Demo rationale: the median move is small compared to the forecast interval, so the edge does not justify a larger position.",
        price: last,
        position_qty: s === 0 ? 1.7 : 0,
        position_value: s === 0 ? 1_240 : 0,
        forecast: {
          median: steps.map((k) => last + drift * k),
          lower: steps.map((k) => last + drift * k - spread * Math.sqrt(k)),
          upper: steps.map((k) => last + drift * k + spread * Math.sqrt(k)),
        },
        verdict: reduced ? "reduced" : verdict,
        risk_reason:
          verdict === "no_order"
            ? "hold: no order"
            : verdict === "blocked"
              ? `no ${symbol} position to sell (long only)`
              : reduced
                ? "buy $640.00, reduced from $1,200.00 by position/exposure limits"
                : "buy $1,000.00",
        order:
          verdict === "accepted"
            ? {
                t: iso(i),
                cycle_id: `demo-${i}`,
                symbol,
                side: "buy",
                qty: 1,
                fill_price: i % 5 === 0 ? null : last + 0.12,
                status: i % 5 === 0 ? "accepted" : "filled",
              }
            : null,
      });
    });
  }
  const last = points[points.length - 1];
  const first = points[0];
  const equity = last?.equity ?? ALLOCATED;
  return {
    status: {
      generated_at: iso(CYCLES - 1),
      state: "active",
      halted_reason: null,
      last_cycle: {
        cycle_id: "demo",
        status: "success",
        detail: "",
        started_at: iso(CYCLES - 1),
        finished_at: iso(CYCLES - 1),
      },
      allocated_capital: ALLOCATED,
      symbols: SYMBOLS,
      capital_floor: 8_000,
      account_size: 100_083.62,
      errors: 2,
      metrics: {
        equity,
        pnl: equity - ALLOCATED,
        total_return: equity / ALLOCATED - 1,
        buy_and_hold_return: (last?.buy_and_hold ?? 1) / (first?.buy_and_hold ?? 1) - 1,
        max_drawdown: 0.0156,
        exposure: last?.exposure ?? 0,
        cash: equity - (last?.exposure ?? 0),
      },
    },
    portfolio: {
      points,
      positions: [
        { symbol: "AAPL", qty: 1.7, market_value: 610, weight: 610 / equity },
        { symbol: "SPY", qty: 1.7, market_value: 1_240, weight: 1_240 / equity },
      ],
    },
    decisions,
    backtest: BACKTEST,
  };
}
