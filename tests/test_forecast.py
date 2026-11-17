from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from agent.config import load_config
from agent.data import PriceSeries
from agent.forecast import (
    ForecastError,
    event_indicator,
    forecast_symbol,
    load_model,
    next_event,
    validate_forecast,
)
from agent.macro import MacroData, Observation

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


def test_event_in_horizon_only_when_a_release_lands_on_a_forecast_bar() -> None:
    forecast = validate_forecast(SERIES, CONFIG, quantiles([98.0, 100.0, 102.0]), LEVELS)
    first_bar = SERIES.last_bar_start + HOUR
    horizon_end = first_bar + CONFIG.horizon * HOUR
    assert not forecast.event_in_horizon
    inside = forecast.model_copy(update={"next_event": first_bar + HOUR})
    assert inside.event_in_horizon
    before = forecast.model_copy(update={"next_event": first_bar - timedelta(minutes=1)})
    after = forecast.model_copy(update={"next_event": horizon_end})
    assert not before.event_in_horizon and not after.event_in_horizon


def test_event_marks_the_bar_that_contains_it() -> None:
    result = event_indicator(BARS, [FIRST_BAR + 2 * HOUR + timedelta(minutes=30)])
    assert result.tolist() == [0, 0, 1, 0, 0, 0]


def test_event_before_open_marks_the_first_bar_after_it() -> None:
    gap = [FIRST_BAR, FIRST_BAR + HOUR, FIRST_BAR + 20 * HOUR]
    assert event_indicator(gap, [FIRST_BAR + 10 * HOUR]).tolist() == [0, 0, 1]


def test_events_outside_the_window_are_ignored() -> None:
    result = event_indicator(BARS, [FIRST_BAR - HOUR, FIRST_BAR + 6 * HOUR])
    assert result.tolist() == [0] * 6


class RecordingForecaster:
    """Stands in for Timestral: records the covariates it receives and returns fixed quantiles."""

    def __init__(self) -> None:
        self.kwargs: dict[str, np.ndarray] = {}

    def forecast(self, context: np.ndarray, **kwargs: np.ndarray) -> SimpleNamespace:
        self.kwargs = kwargs
        row = torch.tensor([98.0, 100.0, 102.0])
        quantiles = row.repeat(CONFIG.horizon, 1)[None, None]
        return SimpleNamespace(quantiles=quantiles, quantile_levels=LEVELS)


def test_forecast_gets_macro_as_past_and_events_as_known_covariates() -> None:
    steps = 400
    start = datetime(2026, 11, 2, tzinfo=UTC)
    stamps = [start + i * HOUR for i in range(steps)]
    series = PriceSeries(
        symbol="SPY", last_bar_start=stamps[-1], timestamps=stamps, values=np.full(steps, 100.0)
    )
    macro = MacroData(
        series={
            "vix": [Observation(date=date(2026, 11, 1), value=20.0)],
            "us10y": [Observation(date=date(2026, 11, 1), value=4.0)],
        }
    )
    forecaster = RecordingForecaster()
    forecast = forecast_symbol(forecaster, series, CONFIG, macro)
    assert forecaster.kwargs["past_covariates"].shape == (1, 2, steps)
    assert forecaster.kwargs["known_covariates"].shape == (1, steps + CONFIG.horizon)
    assert forecast.macro == {"vix": 20.0, "us10y": 4.0}
    assert forecast.next_event is not None and forecast.next_event > stamps[-1]


def test_signal_strength_is_the_signal_over_the_strong_signal_capped_at_one() -> None:
    steps = 400
    stamps = [datetime(2026, 11, 2, tzinfo=UTC) + i * HOUR for i in range(steps)]
    series = PriceSeries(
        symbol="SPY", last_bar_start=stamps[-1], timestamps=stamps, values=np.full(steps, 100.0)
    )
    macro = MacroData(series={"vix": [Observation(date=date(2026, 11, 1), value=20.0)]})
    forecast = forecast_symbol(RecordingForecaster(), series, CONFIG, macro)
    expected = min(1.0, abs(forecast.signal) / CONFIG.signal_strong)
    assert forecast.signal_strength == pytest.approx(expected)


def test_next_event_is_the_first_release_after_the_last_bar() -> None:
    early, late = FIRST_BAR + HOUR, FIRST_BAR + 3 * HOUR
    assert next_event(FIRST_BAR, [late, early, FIRST_BAR - HOUR]) == early
    assert next_event(late, [early]) is None


class FlakyLoader:
    def __init__(self, errors: list[OSError]) -> None:
        self.errors = errors
        self.calls = 0

    def __call__(self, name: str) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "weights"


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.retry.time.sleep", lambda seconds: None)


def patch_loader(monkeypatch: pytest.MonkeyPatch, loader: FlakyLoader) -> None:
    monkeypatch.setattr("agent.forecast.TimestralForecaster.from_pretrained", loader)


@pytest.mark.usefixtures("no_sleep")
def test_transient_load_error_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    loader = FlakyLoader([ConnectionError("offline")])
    patch_loader(monkeypatch, loader)
    assert load_model(CONFIG) == "weights" and loader.calls == 2


@pytest.mark.usefixtures("no_sleep")
def test_persistent_load_error_becomes_a_forecast_error(monkeypatch: pytest.MonkeyPatch) -> None:
    loader = FlakyLoader([TimeoutError()] * CONFIG.max_attempts)
    patch_loader(monkeypatch, loader)
    with pytest.raises(ForecastError, match="unavailable"):
        load_model(CONFIG)
    assert loader.calls == CONFIG.max_attempts


@pytest.mark.usefixtures("no_sleep")
def test_non_transient_load_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    loader = FlakyLoader([PermissionError("denied")])
    patch_loader(monkeypatch, loader)
    with pytest.raises(ForecastError):
        load_model(CONFIG)
    assert loader.calls == 1
