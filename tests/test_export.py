import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.config import load_config
from agent.export import build_export, write_export
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
                "signal_strength": 0.8,
                **HORIZON_PATH,
            }
        ),
    )
    decision = {
        "action": action,
        "size_fraction": 0.5,
        "rationale": "= Median above price.",
    }
    store.save_step(
        cycle_id,
        CYCLE_SCOPE,
        "decisions",
        json.dumps({"decisions": [{"symbol": "SPY", "decision": decision}]}),
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
    expected_costs = 1.0 * 510.25 * CONFIG.backtest.cost_bps / 10_000
    assert metrics.estimated_costs == pytest.approx(expected_costs)
    assert [p.cycle_id for p in export.portfolio.points] == ["c1", "c2"]


def test_decision_card_content(tmp_path: Path) -> None:
    export = build_export(seeded_store(tmp_path), CONFIG, NOW)
    first, second = export.decisions
    assert first.verdict == "accepted" and first.order is None
    assert second.verdict == "reduced" and second.price == 510.0
    assert second.forecast is not None and second.forecast.median == [501.0, 502.0]
    assert second.order is not None and second.order.fill_price == 510.25


def test_hold_and_blocked_verdicts(tmp_path: Path) -> None:
    store = Store(tmp_path / "j.db")
    seed_cycle(store, "c1", 10_000.0, 500.0, action="hold")
    seed_cycle(store, "c2", 10_000.0, 500.0, approved=False)
    verdicts = [d.verdict for d in build_export(store, CONFIG, NOW).decisions]
    assert verdicts == ["no_order", "blocked"]


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
    assert read_lines(out / "trades.csv")[1] == (
        "2026-11-16 15:07:30,c2,SPY,buy,,,1.0,510.25,filled"
    )
    decisions = read_lines(out / "decisions.csv")
    assert decisions[0].startswith("timestamp_utc,cycle_id,symbol,action,signal_strength,")
    assert decisions[1].endswith("'= Median above price.")  # formula neutralized for Excel


def test_simulated_cycles_are_never_exported(tmp_path: Path) -> None:
    store = seeded_store(tmp_path)
    seed_cycle(store, "sim-c3", 5_000.0, 400.0)
    export = build_export(store, CONFIG, NOW)
    assert [d.cycle_id for d in export.decisions] == ["c1", "c2"]
    assert [p.cycle_id for p in export.portfolio.points] == ["c1", "c2"]
    assert export.status.last_cycle is not None and export.status.last_cycle.cycle_id == "c2"
    assert export.status.metrics.equity == 9_900.0
