from datetime import UTC, datetime, timedelta

import pytest

from agent.broker import Bar
from agent.config import load_config
from agent.data import DataError, build_series, check_freshness

MARKET = load_config().market
START = datetime(2026, 11, 10, 14, tzinfo=UTC)


def make_bars(count: int, skip: set[int] | None = None) -> list[Bar]:
    return [
        Bar(symbol="SPY", timestamp=START + timedelta(hours=i), close=100.0 + i)
        for i in range(count)
        if i not in (skip or set())
    ]


def test_intraday_gap_becomes_nan() -> None:
    now = START + timedelta(hours=10)
    series = build_series("SPY", make_bars(8, skip={3}), 8, now, MARKET)
    assert len(series.values) == 8
    assert str(series.values[3]) == "nan"


def test_in_progress_bar_is_dropped() -> None:
    now = START + timedelta(hours=5, minutes=30)
    series = build_series("SPY", make_bars(8), 5, now, MARKET)
    assert series.last_bar_start == START + timedelta(hours=4)


def test_too_few_bars_rejected() -> None:
    with pytest.raises(DataError):
        build_series("SPY", make_bars(3), 10, START + timedelta(hours=5), MARKET)


def test_stale_data_rejected() -> None:
    series = build_series("SPY", make_bars(8), 8, START + timedelta(hours=8), MARKET)
    with pytest.raises(DataError):
        check_freshness(series, START + timedelta(hours=20), MARKET)
