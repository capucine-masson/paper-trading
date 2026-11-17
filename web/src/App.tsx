import { useEffect, useMemo, useState } from "react";
import { loadDashboard } from "./api";
import { Decisions } from "./components/Decisions";
import { ErrorState, Loading } from "./components/Feedback";
import { Header } from "./components/Header";
import { Overview } from "./components/Overview";
import { Quality } from "./components/Quality";
import { useTheme, useViewState } from "./hooks";
import { ALL_SYMBOLS, type DashboardData } from "./types";

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
    () => (data === null ? [] : [...new Set(data.decisions.map((d) => d.symbol))].sort()),
    [data],
  );
  const fitScreen = (view.tab === "overview" || view.tab === "quality") && data !== null;

  return (
    <>
      <Header
        tab={view.tab}
        state={data?.status.state ?? null}
        theme={theme}
        onTab={(tab) => updateView({ tab, symbol: ALL_SYMBOLS })}
        onToggleTheme={toggleTheme}
      />
      <main className={fitScreen ? "content content-fit" : "content"}>
        {load.kind === "loading" && <Loading />}
        {load.kind === "error" && <ErrorState message={load.message} />}
        {data !== null && view.tab === "overview" && (
          <Overview
            status={data.status}
            portfolio={data.portfolio}
            decisions={data.decisions}
            symbol={view.symbol}
            period={view.period}
            onSymbol={(symbol) => updateView({ symbol })}
            onPeriod={(period) => updateView({ period })}
          />
        )}
        {data !== null && view.tab === "decisions" && (
          <Decisions
            decisions={data.decisions}
            symbols={symbols}
            symbol={view.symbol}
            onSymbol={(symbol) => updateView({ symbol })}
          />
        )}
        {data !== null && view.tab === "quality" && (
          <Quality
            backtest={data.backtest}
            symbol={view.symbol}
            onSymbol={(symbol) => updateView({ symbol })}
          />
        )}
      </main>
    </>
  );
}
