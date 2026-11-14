"""Hourly price series: validation, gap marking and freshness checks (no look-ahead)."""

from datetime import datetime, timedelta

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from agent.broker import Bar
from agent.config import MarketConfig

BAR_PERIOD = timedelta(hours=1)


class DataError(Exception):
    """Raised when the price history cannot be trusted; the symbol gets no decision."""


class PriceSeries(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    last_bar_start: datetime
    values: NDArray[np.float64]

    @property
    def last_price(self) -> float:
        return float(self.values[-1])


def build_series(
    symbol: str, bars: list[Bar], context_length: int, now: datetime, market: MarketConfig
) -> PriceSeries:
    """Build the context window from completed bars only; missing intraday bars become NaN."""
    completed = {b.timestamp: b.close for b in bars if b.symbol == symbol}
    completed = {t: c for t, c in completed.items() if t + BAR_PERIOD <= now}
    if not completed:
        raise DataError(f"{symbol}: no completed bar available")
    timestamps = sorted(completed)
    values: list[float] = []
    previous: datetime | None = None
    for timestamp in timestamps:
        if previous is not None and previous.date() == timestamp.date():
            missing = int((timestamp - previous) / BAR_PERIOD) - 1
            values.extend([float("nan")] * missing)
        values.append(completed[timestamp])
        previous = timestamp
    window = np.array(values[-context_length:], dtype=np.float64)
    _check_quality(symbol, window, context_length, market)
    series = PriceSeries(symbol=symbol, last_bar_start=timestamps[-1], values=window)
    return series


def _check_quality(
    symbol: str, window: NDArray[np.float64], context_length: int, market: MarketConfig
) -> None:
    if len(window) < context_length:
        raise DataError(f"{symbol}: only {len(window)} bars, {context_length} required")
    if not np.isfinite(window[-1]) or window[-1] <= 0:
        raise DataError(f"{symbol}: invalid last price")
    gap_ratio = float(np.isnan(window).mean())
    if gap_ratio > market.max_gap_ratio:
        raise DataError(
            f"{symbol}: {gap_ratio:.0%} missing bars exceeds {market.max_gap_ratio:.0%}"
        )


def check_freshness(series: PriceSeries, now: datetime, market: MarketConfig) -> None:
    age = now - series.last_bar_start
    if age > timedelta(hours=market.max_bar_age_hours):
        raise DataError(f"{series.symbol}: last bar is {age} old, data is stale")
