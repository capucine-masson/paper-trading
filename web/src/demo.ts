import type { DashboardData, DecisionView, EquityPoint, ForecastView } from "./types";

// Development-only sample data to preview the layout (open /?demo=1). Never bundled in production.
const SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GLD"];
const BASE_PRICES: Record<string, number> = { SPY: 750, QQQ: 675, AAPL: 355, MSFT: 524, GLD: 355 };
const CYCLES = 18;
const HOUR_MS = 3_600_000;
const ALLOCATED = 10_000;
const ACTIONS: DecisionView["action"][] = ["hold", "buy", "hold", "sell", "hold"];

export function buildDemoData(): DashboardData {
  const end = Date.now();
  const iso = (i: number) => new Date(end - (CYCLES - 1 - i) * HOUR_MS).toISOString();
  const points: EquityPoint[] = [];
  const decisions: DecisionView[] = [];
  const forecasts: ForecastView[] = [];
  for (let i = 0; i < CYCLES; i++) {
    const equity = ALLOCATED + 120 * Math.sin(i / 3) + i * 9;
    points.push({
      t: iso(i),
      equity,
      pnl: equity - ALLOCATED,
      exposure: 1_500 + 80 * i,
      positions: { SPY: 900 + 20 * i, AAPL: 600 + 10 * i },
    });
    SYMBOLS.forEach((symbol, s) => {
      const last = (BASE_PRICES[symbol] ?? 100) * (1 + 0.002 * Math.sin(i / 2 + s));
      const spread = last * (0.012 + 0.002 * s);
      const action = ACTIONS[(i + s) % ACTIONS.length] ?? "hold";
      forecasts.push({
        t: iso(i),
        cycle_id: `demo-${i}`,
        symbol,
        model: "mistralai/Timestral-28M",
        last_bar_start: iso(i),
        horizon_steps: 6,
        last_price: last,
        median: last * (1 + 0.0004 * (s - 2)),
        lower: last - spread,
        upper: last + spread,
        uncertainty: (2 * spread) / last,
      });
      decisions.push({
        t: iso(i),
        cycle_id: `demo-${i}`,
        symbol,
        action,
        confidence: 0.6 + 0.05 * ((i + s) % 6),
        rationale: "Demo rationale: the median move is small compared to the forecast interval.",
        approved: action !== "hold",
        risk_reason: action === "hold" ? "hold: no order" : "buy $1,000.00",
        order_status: action === "hold" ? null : "accepted",
        client_order_id: action === "hold" ? null : `demo-${i}-${symbol}`,
      });
    });
  }
  const last = points[points.length - 1];
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
      equity: last?.equity ?? ALLOCATED,
      pnl: last?.pnl ?? 0,
      rules: [
        { id: "capital_floor", label: "Capital floor", kind: "min", unit: "usd", limit: 8_000, used: last?.equity ?? null, breached: false },
        { id: "daily_loss", label: "Daily loss", kind: "max", unit: "usd", limit: 500, used: 120, breached: false },
        { id: "position", label: "Largest position", kind: "max", unit: "usd", limit: 2_000, used: 1_260, breached: false },
        { id: "exposure", label: "Total exposure", kind: "max", unit: "usd", limit: 8_000, used: last?.exposure ?? 0, breached: false },
        { id: "orders", label: "Orders in last cycle", kind: "max", unit: "count", limit: 5, used: 2, breached: false },
        { id: "uncertainty", label: "Forecast uncertainty", kind: "max", unit: "ratio", limit: 0.06, used: 0.034, breached: false },
      ],
    },
    portfolio: {
      points,
      positions: [
        { symbol: "AAPL", qty: 1.7, market_value: 610 },
        { symbol: "SPY", qty: 1.7, market_value: 1_240 },
      ],
    },
    decisions,
    forecasts,
  };
}
