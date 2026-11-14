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
const ORDER_NOTIONAL = 110;
const MIN_CONFIDENCE = 0.6;
const BLOCKED_CONFIDENCE = 0.55;
const ACTIONS: DecisionView["action"][] = ["hold", "buy", "hold", "sell", "hold"];
const VERDICTS: VerdictStatus[] = ["no_order", "accepted", "no_order", "blocked", "no_order"];

function demoRationale(
  symbol: string,
  action: DecisionView["action"],
  move: number,
  width: number,
): string {
  const pct = (value: number) => `${Math.abs(value * 100).toFixed(1)}%`;
  const direction = move >= 0 ? "rise" : "fall";
  const outlook = `The model expects ${symbol} to ${direction} by about ${pct(move)} over the next ${HORIZON} hours, but outcomes could range about ${pct(width)} around that estimate.`;
  if (action === "buy") return `${outlook} The expected gain is modest but positive, so the model recommends buying.`;
  if (action === "sell") return `${outlook} The expected loss is a risk worth avoiding, so the model recommends selling.`;
  return `${outlook} That move is small compared to the uncertainty, so the model recommends waiting.`;
}

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
  const priceAt = (symbol: string, s: number, i: number) =>
    (BASE_PRICES[symbol] ?? 100) * (1 + 0.002 * Math.sin(i / 2 + s));
  // Quantities come from the demo orders, so positions, exposure and order markers agree.
  const held: Record<string, number> = {};
  let heldAtLastCycle: Record<string, number> = {};
  for (let i = 0; i < CYCLES; i++) {
    const equity = ALLOCATED + 120 * Math.sin(i / 3) + i * 9;
    const spy = ALLOCATED * (1 + 0.0006 * i + 0.004 * Math.sin(i / 2));
    const prices = Object.fromEntries(SYMBOLS.map((symbol, s) => [symbol, priceAt(symbol, s, i)]));
    const positions = Object.fromEntries(
      SYMBOLS.flatMap((symbol) =>
        (held[symbol] ?? 0) > 0 ? [[symbol, (held[symbol] ?? 0) * (prices[symbol] ?? 0)]] : [],
      ),
    );
    heldAtLastCycle = { ...held };
    points.push({
      t: iso(i),
      cycle_id: `demo-${i}`,
      equity,
      buy_and_hold: spy,
      exposure: Object.values(positions).reduce((sum, value) => sum + value, 0),
      positions,
      prices,
    });
    const cycleOrders: { symbol: string; qty: number }[] = [];
    SYMBOLS.forEach((symbol, s) => {
      const last = priceAt(symbol, s, i);
      const spread = last * (0.004 + 0.001 * s);
      const drift = last * 0.0004 * (s - 2);
      const steps = Array.from({ length: HORIZON }, (_, k) => k + 1);
      const action = ACTIONS[(i + s) % ACTIONS.length] ?? "hold";
      const verdict = VERDICTS[(i + s) % VERDICTS.length] ?? "no_order";
      const reduced = verdict === "accepted" && i % 4 === 0;
      const confidence = verdict === "blocked" ? BLOCKED_CONFIDENCE : MIN_CONFIDENCE + 0.05 * ((i + s) % 6);
      const heldQty = held[symbol] ?? 0;
      const qty = ORDER_NOTIONAL / last;
      if (verdict === "accepted") cycleOrders.push({ symbol, qty });
      decisions.push({
        t: iso(i),
        cycle_id: `demo-${i}`,
        symbol,
        action,
        confidence,
        rationale: demoRationale(symbol, action, (drift * HORIZON) / last, (2 * spread * Math.sqrt(HORIZON)) / last),
        price: last,
        position_qty: Number(heldQty.toFixed(3)),
        position_value: heldQty * last,
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
              ? `confidence ${confidence.toFixed(2)} below ${MIN_CONFIDENCE.toFixed(2)}`
              : reduced
                ? `buy $${ORDER_NOTIONAL}.00, reduced from $200.00 by position/exposure limits`
                : `buy $${ORDER_NOTIONAL}.00`,
        order:
          verdict === "accepted"
            ? {
                t: iso(i),
                cycle_id: `demo-${i}`,
                symbol,
                side: "buy",
                qty: Number(qty.toFixed(3)),
                fill_price: i % 5 === 0 ? null : last + 0.12,
                status: i % 5 === 0 ? "accepted" : "filled",
              }
            : null,
      });
    });
    for (const order of cycleOrders) held[order.symbol] = (held[order.symbol] ?? 0) + order.qty;
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
      positions: SYMBOLS.flatMap((symbol) => {
        const qty = heldAtLastCycle[symbol] ?? 0;
        const marketValue = qty * (last?.prices[symbol] ?? 0);
        return qty > 0 ? [{ symbol, qty, market_value: marketValue, weight: marketValue / equity }] : [];
      }),
    },
    decisions,
    backtest: BACKTEST,
  };
}
