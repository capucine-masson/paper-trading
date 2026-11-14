import json
from datetime import UTC, datetime
from pathlib import Path

from agent.config import load_config
from agent.export import build_export, write_export
from agent.store import CYCLE_SCOPE, Store

NOW = datetime(2026, 11, 16, 16, tzinfo=UTC)
CONFIG = load_config()


def seeded_store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "j.db")
    store.start_cycle("c1")
    store.save_step(
        "c1",
        CYCLE_SCOPE,
        "portfolio",
        json.dumps(
            {
                "equity": 9_900.0,
                "day_start_equity": 10_000.0,
                "exposure": 1_000.0,
                "positions": {"SPY": {"qty": 2.0, "market_value": 1_000.0}},
                "halted_reason": None,
            }
        ),
    )
    store.save_step(
        "c1",
        "SPY",
        "forecast",
        json.dumps(
            {
                "symbol": "SPY",
                "model": "m",
                "last_bar_start": "2026-11-16T15:00:00+00:00",
                "last_price": 500.0,
                "median": [501.0],
                "lower": [495.0],
                "upper": [507.0],
                "uncertainty": 0.024,
            }
        ),
    )
    store.save_step(
        "c1",
        "SPY",
        "llm",
        json.dumps({"action": "buy", "confidence": 0.8, "rationale": "Median above price."}),
    )
    store.save_step("c1", "SPY", "verdict", json.dumps({"approved": True, "reason": "buy $500.00"}))
    store.finish_cycle("c1", "success", "")
    return store


def test_export_content(tmp_path: Path) -> None:
    export = build_export(seeded_store(tmp_path), CONFIG, NOW)
    assert export.status.state == "active"
    assert export.status.pnl == -100.0
    assert export.status.last_cycle is not None and export.status.last_cycle.status == "success"
    assert export.decisions[0].approved is True and export.decisions[0].order_status is None
    rules = {r.id: r for r in export.status.rules}
    assert rules["exposure"].used == 1_000.0 and rules["exposure"].limit == 8_000.0
    assert rules["daily_loss"].used == 100.0 and not rules["daily_loss"].breached
    assert rules["orders"].used == 1


def test_halted_state_is_exported(tmp_path: Path) -> None:
    store = seeded_store(tmp_path)
    store.set_state("halted_reason", "below floor")
    export = build_export(store, CONFIG, NOW)
    assert export.status.state == "halted" and export.status.halted_reason == "below floor"


def test_empty_journal_exports_empty_dashboard(tmp_path: Path) -> None:
    export = build_export(Store(tmp_path / "j.db"), CONFIG, NOW)
    assert export.status.equity is None and export.decisions == []
    assert all(rule.used is None for rule in export.status.rules[:4])


def test_files_are_written(tmp_path: Path) -> None:
    out = tmp_path / "data"
    write_export(build_export(seeded_store(tmp_path), CONFIG, NOW), out)
    names = {p.name for p in out.iterdir()}
    assert {"status.json", "portfolio.json", "decisions.json", "decisions.csv"} <= names
    assert json.loads((out / "decisions.json").read_text())[0]["symbol"] == "SPY"
