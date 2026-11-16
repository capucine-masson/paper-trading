export type AgentState = "active" | "halted" | "stopped";
export type VerdictStatus = "accepted" | "reduced" | "blocked" | "no_order";

export interface CycleView {
  cycle_id: string;
  status: string | null;
  detail: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface Metrics {
  equity: number | null;
  pnl: number | null;
  total_return: number | null;
  buy_and_hold_return: number | null;
  max_drawdown: number | null;
  exposure: number | null;
  cash: number | null;
}

export interface Status {
  generated_at: string;
  state: AgentState;
  halted_reason: string | null;
  last_cycle: CycleView | null;
  allocated_capital: number;
  symbols: string[];
  capital_floor: number;
  account_size: number | null;
  metrics: Metrics;
}

export interface EquityPoint {
  t: string;
  cycle_id: string;
  equity: number;
  buy_and_hold: number | null;
  exposure: number;
  positions: Record<string, number>;
  prices: Record<string, number>;
}

export interface PositionView {
  symbol: string;
  qty: number;
  market_value: number;
  weight: number;
}

export interface PortfolioData {
  points: EquityPoint[];
  positions: PositionView[];
}

export interface TradeView {
  t: string;
  cycle_id: string;
  symbol: string;
  side: string;
  qty: number | null;
  fill_price: number | null;
  status: string;
}

export interface ForecastPath {
  median: number[];
  lower: number[];
  upper: number[];
}

export interface DecisionView {
  t: string;
  cycle_id: string;
  symbol: string;
  action: "buy" | "sell" | "hold";
  confidence: number;
  size_fraction: number;
  rationale: string;
  price: number | null;
  position_qty: number;
  position_value: number;
  forecast: ForecastPath | null;
  verdict: VerdictStatus;
  risk_reason: string | null;
  order: TradeView | null;
}

export interface ForecastMetrics {
  n: number;
  mae_ratio: number | null;
  coverage: number;
}

export interface ModelResult {
  label: string;
  model: string;
  overall: ForecastMetrics;
  per_symbol: Record<string, ForecastMetrics>;
}

export interface ForecastPoint {
  t: string;
  symbol: string;
  lower: number;
  median: number;
  upper: number;
  actual: number;
}

export interface BacktestReport {
  symbols: string[];
  horizon_bars: number;
  history_start: string;
  history_end: string;
  models: ModelResult[];
  forecasts: ForecastPoint[];
}

export interface DashboardData {
  status: Status;
  portfolio: PortfolioData;
  decisions: DecisionView[];
  backtest: BacktestReport | null;
}

export type Period = "1d" | "3d" | "all";
export type Theme = "light" | "dark";
export type Tab = "overview" | "decisions" | "quality";
export const ALL_SYMBOLS = "all";
