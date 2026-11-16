"""Hourly price series: validation, gap marking and freshness checks (no look-ahead)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from agent.config import MarketConfig

BAR_PERIOD = timedelta(hours=1)
MARKET_TIMEZONE = ZoneInfo("America/New_York")
WEEKDAYS_PER_WEEK = 5


class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    close: float


class DataError(Exception):
    """Raised when the price history cannot be trusted; the symbol gets no decision."""


class PriceSeries(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    last_bar_start: datetime
    timestamps: list[datetime]
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
    starts: list[datetime] = []
    previous: datetime | None = None
    for timestamp in timestamps:
        if previous is not None and previous.date() == timestamp.date():
            missing = int((timestamp - previous) / BAR_PERIOD) - 1
            values.extend([float("nan")] * missing)
            starts.extend(previous + BAR_PERIOD * (k + 1) for k in range(missing))
        values.append(completed[timestamp])
        starts.append(timestamp)
        previous = timestamp
    window = np.array(values[-context_length:], dtype=np.float64)
    _check_quality(symbol, window, context_length, market)
    return PriceSeries(
        symbol=symbol,
        last_bar_start=timestamps[-1],
        timestamps=starts[-context_length:],
        values=window,
    )


def future_bar_starts(series: PriceSeries, count: int) -> list[datetime]:
    """Next bar starts: weekday hours seen in the context (New York time); holidays not modelled."""
    seen_hours = {t.astimezone(MARKET_TIMEZONE).hour for t in series.timestamps}
    starts: list[datetime] = []
    candidate = series.timestamps[-1]
    while len(starts) < count:
        candidate += BAR_PERIOD
        local = candidate.astimezone(MARKET_TIMEZONE)
        if local.weekday() < WEEKDAYS_PER_WEEK and local.hour in seen_hours:
            starts.append(candidate)
    return starts


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
