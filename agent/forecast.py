"""Timestral forecasting with strict validation of the output."""

from datetime import datetime

import numpy as np
import torch
from numpy.typing import NDArray
from pydantic import BaseModel
from timestral import TimestralForecaster

from agent.config import ForecastConfig
from agent.data import PriceSeries

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


def load_model(name: str) -> TimestralForecaster:
    return TimestralForecaster.from_pretrained(name)


def forecast_symbol(
    forecaster: TimestralForecaster,
    series: PriceSeries,
    config: ForecastConfig,
    news_count: NDArray[np.float64] | None = None,
) -> PriceForecast:
    """With `news_count`, the article counts are given to Timestral as a past-only covariate."""
    with torch.no_grad():
        if news_count is None:
            result = forecaster.forecast(series.values, prediction_length=config.horizon)
        else:
            if news_count.shape != series.values.shape:
                raise ForecastError(f"{series.symbol}: news covariate does not match the series")
            result = forecaster.forecast(
                series.values[np.newaxis, np.newaxis, :],
                prediction_length=config.horizon,
                past_covariates=news_count[np.newaxis, np.newaxis, :],
            )
    quantiles = result.quantiles.numpy()[0, 0]
    return validate_forecast(series, config, quantiles, result.quantile_levels)


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
