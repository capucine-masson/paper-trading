from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from agent.config import load_config
from agent.data import PriceSeries
from agent.forecast import ForecastError, event_indicator, validate_forecast

CONFIG = load_config().forecast
LEVELS = (0.1, 0.5, 0.9)
SERIES = PriceSeries(
    symbol="SPY",
    last_bar_start=datetime(2026, 11, 10, tzinfo=UTC),
    timestamps=[datetime(2026, 11, 10, tzinfo=UTC)],
    values=np.array([100.0]),
)
HOUR = timedelta(hours=1)
FIRST_BAR = datetime(2026, 11, 10, 14, tzinfo=UTC)
BARS = [FIRST_BAR + i * HOUR for i in range(6)]


def quantiles(row: list[float]) -> np.ndarray:
    return np.tile(np.array(row), (CONFIG.horizon, 1))


def test_valid_forecast() -> None:
    result = validate_forecast(SERIES, CONFIG, quantiles([98.0, 100.0, 102.0]), LEVELS)
    assert result.uncertainty == pytest.approx(0.04)
    assert result.signal == pytest.approx((result.median[-1] / result.last_price - 1) / 0.04)


def test_non_finite_rejected() -> None:
    with pytest.raises(ForecastError):
        validate_forecast(SERIES, CONFIG, quantiles([98.0, np.nan, 102.0]), LEVELS)


def test_decreasing_quantiles_rejected() -> None:
    with pytest.raises(ForecastError):
        validate_forecast(SERIES, CONFIG, quantiles([102.0, 100.0, 98.0]), LEVELS)


def test_flat_interval_is_rejected() -> None:
    with pytest.raises(ForecastError, match="no width"):
        validate_forecast(SERIES, CONFIG, quantiles([100.0, 100.0, 100.0]), LEVELS)


def test_event_marks_the_bar_that_contains_it() -> None:
    result = event_indicator(BARS, [FIRST_BAR + 2 * HOUR + timedelta(minutes=30)])
    assert result.tolist() == [0, 0, 1, 0, 0, 0]


def test_event_before_open_marks_the_first_bar_after_it() -> None:
    gap = [FIRST_BAR, FIRST_BAR + HOUR, FIRST_BAR + 20 * HOUR]
    assert event_indicator(gap, [FIRST_BAR + 10 * HOUR]).tolist() == [0, 0, 1]


def test_events_outside_the_window_are_ignored() -> None:
    result = event_indicator(BARS, [FIRST_BAR - HOUR, FIRST_BAR + 6 * HOUR])
    assert result.tolist() == [0] * 6
