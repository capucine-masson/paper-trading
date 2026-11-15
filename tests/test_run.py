from datetime import UTC, datetime

import pytest

from agent import run
from agent.store import is_simulation

NOW = datetime(2026, 11, 16, 15, 7, tzinfo=UTC)


def test_executed_cycle_id_is_the_utc_hour() -> None:
    assert run.default_cycle_id(True, NOW) == "20261116T15"


def test_simulated_cycle_id_is_marked() -> None:
    cycle_id = run.default_cycle_id(False, NOW)
    assert cycle_id == "sim-20261116T15" and is_simulation(cycle_id)


def test_orders_cannot_be_sent_with_the_market_clock_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["run", "--once", "--execute", "--ignore-market-clock"])
    with pytest.raises(SystemExit):
        run._parse_args()
