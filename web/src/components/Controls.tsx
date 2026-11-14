import { ALL_SYMBOLS, type Period } from "../types";

const PERIOD_LABELS: { value: Period; label: string }[] = [
  { value: "1d", label: "1 day" },
  { value: "3d", label: "3 days" },
  { value: "all", label: "All" },
];

interface Props {
  period: Period;
  symbol: string;
  symbols: string[];
  onChange: (next: { period?: Period; symbol?: string }) => void;
}

export function Controls({ period, symbol, symbols, onChange }: Props) {
  return (
    <div className="controls">
      <label>
        Period
        <select value={period} onChange={(e) => onChange({ period: e.target.value as Period })}>
          {PERIOD_LABELS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Symbol
        <select value={symbol} onChange={(e) => onChange({ symbol: e.target.value })}>
          <option value={ALL_SYMBOLS}>All symbols</option>
          {symbols.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
