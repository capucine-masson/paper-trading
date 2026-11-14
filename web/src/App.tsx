import { useEffect, useMemo, useState } from "react";
import { isDemo, loadDashboard } from "./api";
import { Controls } from "./components/Controls";
import { Decisions } from "./components/Decisions";
import { Exports } from "./components/Exports";
import { ErrorState, Loading } from "./components/Feedback";
import { Forecasts } from "./components/Forecasts";
import { Header } from "./components/Header";
import { Portfolio } from "./components/Portfolio";
import { Rules } from "./components/Rules";
import { StatusPanel } from "./components/StatusPanel";
import { forSymbol, inPeriod, latestPerSymbol } from "./filters";
import { useTheme, useViewState } from "./hooks";
import type { DashboardData } from "./types";

type Load = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: DashboardData };

export function App() {
  const [theme, toggleTheme] = useTheme();
  const [view, updateView] = useViewState();
  const [load, setLoad] = useState<Load>({ kind: "loading" });

  useEffect(() => {
    loadDashboard()
      .then((data) => setLoad({ kind: "ready", data }))
      .catch((error: unknown) =>
        setLoad({ kind: "error", message: error instanceof Error ? error.message : "Unknown error" }),
      );
  }, []);

  const data = load.kind === "ready" ? load.data : null;
  const symbols = useMemo(
    () => (data === null ? [] : [...new Set(data.forecasts.map((f) => f.symbol))].sort()),
    [data],
  );

  return (
    <main className="page">
      <Header state={data?.status.state ?? null} theme={theme} onToggleTheme={toggleTheme} />
      {isDemo() && <p className="notice notice-halted">Demo data for layout preview only (development).</p>}
      {load.kind === "loading" && <Loading />}
      {load.kind === "error" && <ErrorState message={load.message} />}
      {data !== null && (
        <Dashboard data={data} symbols={symbols} view={view} onChange={updateView} />
      )}
    </main>
  );
}

interface DashboardProps {
  data: DashboardData;
  symbols: string[];
  view: ReturnType<typeof useViewState>[0];
  onChange: ReturnType<typeof useViewState>[1];
}

function Dashboard({ data, symbols, view, onChange }: DashboardProps) {
  const reference = data.status.generated_at;
  const points = inPeriod(data.portfolio.points, view.period, reference);
  const decisions = forSymbol(inPeriod(data.decisions, view.period, reference), view.symbol);
  const forecasts = latestPerSymbol(
    forSymbol(inPeriod(data.forecasts, view.period, reference), view.symbol),
  );
  const positions = forSymbol(data.portfolio.positions, view.symbol);
  return (
    <>
      <Controls period={view.period} symbol={view.symbol} symbols={symbols} onChange={onChange} />
      <div className="grid">
        <StatusPanel status={data.status} />
        <Rules rules={data.status.rules} />
      </div>
      <Portfolio points={points} positions={positions} symbol={view.symbol} />
      <Decisions decisions={decisions} />
      <Forecasts forecasts={forecasts} />
      <Exports />
    </>
  );
}
