import { TABS } from "../hooks";
import type { AgentState, Tab, Theme } from "../types";

const STATE_LABEL: Record<AgentState, string> = {
  active: "Active",
  halted: "Halted",
  stopped: "Emergency stop",
};

interface Props {
  tab: Tab;
  state: AgentState | null;
  theme: Theme;
  onTab: (tab: Tab) => void;
  onToggleTheme: () => void;
}

export function Header({ tab, state, theme, onTab, onToggleTheme }: Props) {
  const nextTheme = theme === "dark" ? "light" : "dark";
  return (
    <header className="topbar">
      <img className="brand" src={`${import.meta.env.BASE_URL}logo-${theme}.png`} alt="Paper Trading Agent" />
      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === tab}
            className="tab"
            onClick={() => onTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="topbar-right">
        {state !== null && <span className={`badge badge-${state}`}>{STATE_LABEL[state]}</span>}
        <button
          type="button"
          className="icon-button"
          onClick={onToggleTheme}
          aria-label={`Switch to ${nextTheme} theme`}
          title={`Switch to ${nextTheme} theme`}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
      </div>
    </header>
  );
}

const ICON_PROPS = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

function SunIcon() {
  return (
    <svg {...ICON_PROPS}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}
