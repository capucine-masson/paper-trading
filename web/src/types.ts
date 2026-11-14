export type AgentState = "active" | "halted" | "stopped";
export type RuleUnit = "usd" | "count" | "ratio";

export interface RuleUsage {
  id: string;
  label: string;
  kind: "max" | "min";
  unit: RuleUnit;
  limit: number;
  used: number | null;
  breached: boolean;
}

export interface CycleView {
  cycle_id: string;
  status: string | null;
  detail: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface Status {
  generated_at: string;
  state: AgentState;
  halted_reason: string | null;
  last_cycle: CycleView | null;
  allocated_capital: number;
  equity: number | null;
  pnl: number | null;
  rules: RuleUsage[];
}

export interface EquityPoint {
  t: string;
  equity: number;
  pnl: number;
  exposure: number;
  positions: Record<string, number>;
}

export interface PositionView {
  symbol: string;
  qty: number;
  market_value: number;
}

export interface PortfolioData {
  points: EquityPoint[];
  positions: PositionView[];
}

export interface DecisionView {
  t: string;
  cycle_id: string;
  symbol: string;
  action: "buy" | "sell" | "hold";
  confidence: number;
  rationale: string;
  approved: boolean | null;
  risk_reason: string | null;
  order_status: string | null;
  client_order_id: string | null;
}

export interface ForecastView {
  t: string;
  cycle_id: string;
  symbol: string;
  model: string;
  last_bar_start: string;
  horizon_steps: number;
  last_price: number;
  median: number;
  lower: number;
  upper: number;
  uncertainty: number;
}

export interface DashboardData {
  status: Status;
  portfolio: PortfolioData;
  decisions: DecisionView[];
  forecasts: ForecastView[];
}

export type Period = "1d" | "3d" | "all";
export type Theme = "light" | "dark";
export const ALL_SYMBOLS = "all";
