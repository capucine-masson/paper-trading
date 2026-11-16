from datetime import UTC, datetime

import numpy as np
import pytest

from agent.config import load_config
from agent.data import PriceSeries
from agent.forecast import ForecastError, validate_forecast

CONFIG = load_config().forecast
LEVELS = (0.1, 0.5, 0.9)
SERIES = PriceSeries(
    symbol="SPY",
    last_bar_start=datetime(2026, 11, 10, tzinfo=UTC),
    values=np.array([100.0]),
)


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
