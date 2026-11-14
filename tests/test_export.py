import json
from datetime import UTC, datetime
from pathlib import Path

from agent.config import load_config
from agent.export import build_export, copy_backtest, write_export
from agent.store import CYCLE_SCOPE, Store

NOW = datetime(2026, 11, 16, 16, tzinfo=UTC)
CONFIG = load_config()
HORIZON_PATH = {"median": [501.0, 502.0], "lower": [495.0, 494.0], "upper": [507.0, 509.0]}


def seed_cycle(
    store: Store,
    cycle_id: str,
    equity: float,
    spy_price: float,
    action: str = "buy",
    **verdict: object,
) -> None:
    store.start_cycle(cycle_id)
    store.save_step(
        cycle_id,
        CYCLE_SCOPE,
        "portfolio",
        json.dumps(
            {
                "equity": equity,
                "day_start_equity": 10_000.0,
                "exposure": 1_000.0,
                "positions": {"SPY": {"qty": 2.0, "market_value": 1_000.0}},
                "halted_reason": None,
            }
        ),
    )
    store.save_step(
        cycle_id,
        "SPY",
        "forecast",
        json.dumps(
            {
                "symbol": "SPY",
                "model": "m",
                "last_bar_start": "2026-11-16T15:00:00+00:00",
                "last_price": spy_price,
                "uncertainty": 0.024,
                **HORIZON_PATH,
            }
        ),
    )
    store.save_step(
        cycle_id,
        "SPY",
        "llm",
        json.dumps({"action": action, "confidence": 0.8, "rationale": "= Median above price."}),
    )
    store.save_step(
        cycle_id,
        "SPY",
        "verdict",
        json.dumps({"approved": True, "reason": "buy $500.00", **verdict}),
    )
    store.finish_cycle(cycle_id, "success", "")


def seeded_store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "j.db")
    seed_cycle(store, "c1", 10_000.0, 500.0)
    seed_cycle(store, "c2", 9_900.0, 510.0, reduced=True)
    store.save_step(
        "c2",
        "SPY",
        "order",
        json.dumps(
            {
                "order_id": "o1",
                "client_order_id": "c2-SPY-buy",
                "symbol": "SPY",
                "side": "buy",
                "status": "filled",
                "filled_qty": 1.0,
                "filled_avg_price": 510.25,
                "filled_at": "2026-11-16T15:07:30+00:00",
            }
        ),
    )
    return store


def test_metrics_and_curve(tmp_path: Path) -> None:
    export = build_export(seeded_store(tmp_path), CONFIG, NOW)
    metrics = export.status.metrics
    assert metrics.equity == 9_900.0 and metrics.pnl == -100.0
    assert metrics.total_return == -0.01 and metrics.cash == 8_900.0
    assert metrics.max_drawdown is not None and abs(metrics.max_drawdown - 0.01) < 1e-9
    assert metrics.buy_and_hold_return is None  # the test config holds more than SPY
    assert export.status.capital_floor == CONFIG.risk.capital_floor
    assert export.status.account_size is None  # no cycle recorded it
    first, second = export.portfolio.points
    assert first.prices == {"SPY": 500.0} and first.buy_and_hold is None
    assert export.status.symbols == CONFIG.market.symbols
    assert second.cycle_id == "c2" and export.portfolio.positions[0].weight == 1_000.0 / 9_900.0


def test_decision_card_content(tmp_path: Path) -> None:
    export = build_export(seeded_store(tmp_path), CONFIG, NOW)
    first, second = export.decisions
    assert first.verdict == "accepted" and first.order is None
    assert second.verdict == "reduced" and second.price == 510.0
    assert second.position_qty == 2.0 and second.forecast is not None
    assert second.forecast.median == [501.0, 502.0]
    assert second.order is not None and second.order.fill_price == 510.25


def test_hold_and_blocked_verdicts(tmp_path: Path) -> None:
    store = Store(tmp_path / "j.db")
    seed_cycle(store, "c1", 10_000.0, 500.0, action="hold")
    seed_cycle(store, "c2", 10_000.0, 500.0, approved=False)
    verdicts = [d.verdict for d in build_export(store, CONFIG, NOW).decisions]
    assert verdicts == ["no_order", "blocked"]


def test_account_size_comes_from_the_journaled_account_equity(tmp_path: Path) -> None:
    store = seeded_store(tmp_path)
    store.set_state("account_equity", "100250.5")
    assert build_export(store, CONFIG, NOW).status.account_size == 100_250.5


def test_halted_state_is_exported(tmp_path: Path) -> None:
    store = seeded_store(tmp_path)
    store.set_state("halted_reason", "below floor")
    export = build_export(store, CONFIG, NOW)
    assert export.status.state == "halted" and export.status.halted_reason == "below floor"


def test_empty_journal_exports_empty_dashboard(tmp_path: Path) -> None:
    export = build_export(Store(tmp_path / "j.db"), CONFIG, NOW)
    assert export.status.metrics.equity is None and export.decisions == []
    assert export.portfolio.points == [] and export.trades == []


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig").splitlines()


def test_csv_files_match_the_requested_columns(tmp_path: Path) -> None:
    out = tmp_path / "data"
    write_export(build_export(seeded_store(tmp_path), CONFIG, NOW), out)
    assert read_lines(out / "trades.csv") == [
        "timestamp,symbol,side,quantity,fill_price,status",
        "2026-11-16 15:07:30,SPY,buy,1.0,510.25,filled",
    ]
    assert read_lines(out / "equity.csv")[0] == "timestamp,equity,buy_and_hold"
    decisions = read_lines(out / "decisions.csv")
    assert decisions[0] == "timestamp,symbol,action,risk_verdict,risk_reason,llm_reasoning"
    assert decisions[1].endswith("'= Median above price.")  # formula neutralized for Excel
    assert json.loads((out / "decisions.json").read_text())[0]["symbol"] == "SPY"


def test_backtest_report_is_copied_only_when_present(tmp_path: Path) -> None:
    out = tmp_path / "data"
    out.mkdir()
    assert not copy_backtest(tmp_path / "missing.json", out)
    report = tmp_path / "backtest.json"
    report.write_text("{}", encoding="utf-8")
    assert copy_backtest(report, out) and (out / "backtest.json").exists()
