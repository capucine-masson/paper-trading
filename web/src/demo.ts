import type {
  BacktestReport,
  DashboardData,
  DecisionView,
  EquityPoint,
  ForecastMetrics,
  ForecastPoint,
  VerdictStatus,
} from "./types";

// Development-only sample data to preview the layout (open /?demo=1). Never bundled in production.
const SYMBOLS = ["SPY", "QQQ", "XLE", "XLF", "XLU", "TLT", "GLD", "EEM"];
const BASE_PRICES: Record<string, number> = {
  SPY: 750,
  QQQ: 675,
  XLE: 65,
  XLF: 59,
  XLU: 44,
  TLT: 79,
  GLD: 355,
  EEM: 61,
};
const CYCLES = 18;
const HORIZON = 6;
const HOUR_MS = 3_600_000;
const ALLOCATED = 10_000;
const ORDER_NOTIONAL = 110;
const MIN_CONFIDENCE = 0.5;
const BLOCKED_CONFIDENCE = 0.45;
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

const stats = (mae_ratio: number, coverage: number): ForecastMetrics => ({
  n: 221,
  mae_ratio,
  coverage,
  direction_hit_rate: 0.51,
});

const DEMO_MACRO = { brent: 82.1, us10y: 4.21, us2y: 4.55, dollar: 121.3, vix: 16.4, hy_spread: 3.05 };
const DEMO_NEXT_EVENT = "2026-12-09T19:00:00Z";
const DEMO_CONTEXT = "The VIX is low and yields are stable, so no strong macro pressure is visible before the next release.";
const DEMO_COST_BPS = 5;
const BPS_PER_UNIT = 10_000;
const DEMO_FORECASTS = 130;
const DEMO_STEP = 0.004;
const DEMO_BAND_Z = 1.2816;
const DEMO_SEED = 13;
const STEPS_AHEAD = 2;
const FORECAST_SPACING_HOURS = 3;

/** Small deterministic generator so the preview never changes between reloads. */
function seededNormal(seed: number): () => number {
  let state = seed;
  const uniform = (): number => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return () => Math.sqrt(-2 * Math.log(1 - uniform())) * Math.cos(2 * Math.PI * uniform());
}

/** Random-walk price; the band is the 80% range of the move to the target, so about 20% fall outside. */
function demoForecasts(): ForecastPoint[] {
  const normal = seededNormal(DEMO_SEED);
  const prices = [BASE_PRICES.SPY ?? 0];
  for (let i = 1; i < DEMO_FORECASTS + STEPS_AHEAD; i += 1) {
    prices.push((prices[i - 1] ?? 0) * (1 + normal() * DEMO_STEP));
  }
  const halfWidth = DEMO_BAND_Z * DEMO_STEP * Math.sqrt(STEPS_AHEAD);
  return Array.from({ length: DEMO_FORECASTS }, (_, i) => {
    const median = prices[i] ?? 0;
    return {
      t: new Date(Date.UTC(2026, 10, 1) + i * FORECAST_SPACING_HOURS * HOUR_MS).toISOString(),
      symbol: "SPY",
      lower: median * (1 - halfWidth),
      median,
      upper: median * (1 + halfWidth),
      actual: prices[i + STEPS_AHEAD] ?? 0,
    };
  });
}

const BACKTEST: BacktestReport = {
  symbols: SYMBOLS,
  forecasts: demoForecasts(),
  horizon_bars: HORIZON,
  history_start: "2026-05-20T12:00:00Z",
  history_end: "2026-11-13T21:00:00Z",
  decision_start: "2026-10-16T14:00:00Z",
  strategies: [
    { name: "Cash (never trade)", return_pct: 0, max_drawdown_pct: 0 },
    { name: "Equal-weight buy and hold", return_pct: -1.13, max_drawdown_pct: 3.18 },
    { name: "Momentum rule", return_pct: -4.29, max_drawdown_pct: 4.5 },
    { name: "Timestral-only rule", return_pct: -0.78, max_drawdown_pct: 4.26 },
    { name: "Timestral + LLM (the agent)", return_pct: -0.23, max_drawdown_pct: 4.85 },
  ],
  models: [
    {
      model: "mistralai/Timestral-28M",
      overall: { n: 1579, mae_ratio: 0.998, coverage: 0.783, direction_hit_rate: 0.51 },
      per_symbol: {
        SPY: stats(0.998, 0.77),
        QQQ: stats(1.004, 0.79),
        XLE: stats(1.003, 0.801),
        XLF: stats(0.996, 0.8),
        XLU: stats(1.001, 0.79),
        TLT: stats(0.999, 0.795),
        GLD: stats(1.0096, 0.786),
        EEM: stats(1.002, 0.782),
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
        size_fraction: action === "buy" ? 0.5 : 0,
        context: DEMO_CONTEXT,
        rationale: demoRationale(symbol, action, (drift * HORIZON) / last, (2 * spread * Math.sqrt(HORIZON)) / last),
        price: last,
        position_qty: Number(heldQty.toFixed(3)),
        position_value: heldQty * last,
        forecast: {
          median: steps.map((k) => last + drift * k),
          lower: steps.map((k) => last + drift * k - spread * Math.sqrt(k)),
          upper: steps.map((k) => last + drift * k + spread * Math.sqrt(k)),
        },
        macro: DEMO_MACRO,
        next_event: DEMO_NEXT_EVENT,
        verdict: reduced ? "reduced" : verdict,
        risk_reason:
          verdict === "no_order"
            ? "hold: no order"
            : verdict === "blocked"
              ? `confidence ${Math.round(confidence * 100)}% below ${Math.round(MIN_CONFIDENCE * 100)}%`
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
                ordered_qty: null,
                notional: ORDER_NOTIONAL,
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
      capital_floor: 5_000,
      account_size: 100_083.62,
      metrics: {
        equity,
        pnl: equity - ALLOCATED,
        total_return: equity / ALLOCATED - 1,
        buy_and_hold_return: (last?.buy_and_hold ?? 1) / (first?.buy_and_hold ?? 1) - 1,
        max_drawdown: 0.0156,
        exposure: last?.exposure ?? 0,
        cash: equity - (last?.exposure ?? 0),
        estimated_costs: (decisions.filter((d) => d.order !== null).length * ORDER_NOTIONAL * DEMO_COST_BPS) / BPS_PER_UNIT,
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
