import type { AgentState, Theme } from "../types";

const STATE_LABEL: Record<AgentState, string> = {
  active: "Active",
  halted: "Halted",
  stopped: "Emergency stop",
};

interface Props {
  state: AgentState | null;
  theme: Theme;
  onToggleTheme: () => void;
}

export function Header({ state, theme, onToggleTheme }: Props) {
  return (
    <header className="header">
      <div>
        <h1>Paper Trading Agent</h1>
        <p className="muted">Timestral forecasts, Mistral decisions, Alpaca paper account. Read-only.</p>
      </div>
      <div className="header-actions">
        {state !== null && <span className={`badge badge-${state}`}>{STATE_LABEL[state]}</span>}
        <button type="button" className="button" onClick={onToggleTheme}>
          {theme === "dark" ? "Light theme" : "Dark theme"}
        </button>
      </div>
    </header>
  );
}
