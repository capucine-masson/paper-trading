"""Timestral forecasting with strict validation of the output."""

import logging
import time
from datetime import datetime

import numpy as np
import torch
from huggingface_hub.errors import HfHubHTTPError, LocalEntryNotFoundError
from numpy.typing import NDArray
from pydantic import BaseModel
from timestral import TimestralForecaster

from agent.config import ForecastConfig
from agent.data import BAR_PERIOD, PriceSeries, future_bar_starts
from agent.macro import MacroData, macro_covariates

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500
LOWER_LEVEL = 0.1
UPPER_LEVEL = 0.9


class ForecastError(Exception):
    """Raised when a forecast is invalid; the symbol gets no decision."""


class PriceForecast(BaseModel):
    symbol: str
    model: str
    last_bar_start: datetime
    last_price: float
    median: list[float]
    lower: list[float]
    upper: list[float]
    uncertainty: float

    @property
    def signal(self) -> float:
        """Expected return at the horizon divided by the interval width: a unitless conviction."""
        return (self.median[-1] / self.last_price - 1) / self.uncertainty


def load_model(config: ForecastConfig) -> TimestralForecaster:
    """Load the weights, retrying only transient Hugging Face errors with an increasing delay."""
    delay = config.retry_delay_s
    attempt = 1
    while True:
        try:
            return TimestralForecaster.from_pretrained(config.model)
        except OSError as error:
            logger.warning(
                "cannot load %s (attempt %d/%d): %r",
                config.model,
                attempt,
                config.max_attempts,
                error,
            )
            if not _is_transient(error) or attempt >= config.max_attempts:
                raise ForecastError(
                    f"Timestral weights {config.model} unavailable ({type(error).__name__})"
                ) from error
        time.sleep(delay)
        delay *= 2
        attempt += 1


def _is_transient(error: OSError) -> bool:
    """Network failure, timeout (a missing cache while offline included), 429 or 5xx."""
    if isinstance(error, HfHubHTTPError):
        status = error.response.status_code
        return status == HTTP_TOO_MANY_REQUESTS or status >= HTTP_SERVER_ERROR
    return isinstance(error, ConnectionError | TimeoutError | LocalEntryNotFoundError)


def forecast_symbol(
    forecaster: TimestralForecaster,
    series: PriceSeries,
    config: ForecastConfig,
    macro: MacroData,
) -> PriceForecast:
    bar_starts = series.timestamps + future_bar_starts(series, config.horizon)
    events = event_indicator(bar_starts, config.event_times)
    drivers = macro_covariates(macro, series.timestamps)
    with torch.no_grad():
        result = forecaster.forecast(
            series.values,
            prediction_length=config.horizon,
            past_covariates=drivers[None, :, :],
            known_covariates=events[None, :],
        )
    quantiles = result.quantiles.numpy()[0, 0]
    return validate_forecast(series, config, quantiles, result.quantile_levels)


def event_indicator(bar_starts: list[datetime], events: list[datetime]) -> NDArray[np.float64]:
    """1.0 on the first bar ending after each event (the bar that absorbs the release), else 0.0."""
    indicator = np.zeros(len(bar_starts))
    for event in events:
        if event < bar_starts[0]:
            continue
        index = next((i for i, start in enumerate(bar_starts) if start + BAR_PERIOD > event), None)
        if index is not None:
            indicator[index] = 1.0
    return indicator


def validate_forecast(
    series: PriceSeries,
    config: ForecastConfig,
    quantiles: NDArray[np.floating],
    levels: tuple[float, ...],
) -> PriceForecast:
    """quantiles has shape (horizon, n_levels)."""
    symbol = series.symbol
    if quantiles.shape != (config.horizon, len(levels)):
        raise ForecastError(f"{symbol}: unexpected forecast shape {quantiles.shape}")
    if not np.isfinite(quantiles).all():
        raise ForecastError(f"{symbol}: forecast contains non-finite values")
    if (np.diff(quantiles, axis=1) < 0).any():
        raise ForecastError(f"{symbol}: forecast quantiles are not increasing")
    median = quantiles[:, levels.index(0.5)]
    lower = quantiles[:, levels.index(LOWER_LEVEL)]
    upper = quantiles[:, levels.index(UPPER_LEVEL)]
    if (lower <= 0).any():
        raise ForecastError(f"{symbol}: forecast lower bound is not positive")
    if upper[-1] <= lower[-1]:
        raise ForecastError(f"{symbol}: forecast interval has no width")
    return PriceForecast(
        symbol=symbol,
        model=config.model,
        last_bar_start=series.last_bar_start,
        last_price=series.last_price,
        median=median.tolist(),
        lower=lower.tolist(),
        upper=upper.tolist(),
        uncertainty=float((upper[-1] - lower[-1]) / median[-1]),
    )
