"""Pure evaluation metrics for forecasts and equity curves."""

import numpy as np
from pydantic import BaseModel


class ForecastSample(BaseModel):
    """One forecast at the horizon and what really happened."""

    last: float
    median: float
    lower: float
    upper: float
    actual: float


class ForecastMetrics(BaseModel):
    n: int
    mae_model: float
    mae_naive: float
    mae_ratio: float
    direction_n: int
    direction_hit_rate: float
    coverage: float
    mean_width: float


def forecast_metrics(samples: list[ForecastSample]) -> ForecastMetrics:
    """The naive forecast is "the price stays at its last value"; mae_ratio below 1 beats it."""
    if not samples:
        raise ValueError("no forecast sample to evaluate")
    last = np.array([s.last for s in samples])
    median = np.array([s.median for s in samples])
    lower = np.array([s.lower for s in samples])
    upper = np.array([s.upper for s in samples])
    actual = np.array([s.actual for s in samples])
    mae_model = float(np.mean(np.abs(median - actual)))
    mae_naive = float(np.mean(np.abs(last - actual)))
    moved = actual != last
    hits = np.sign(median - last)[moved] == np.sign(actual - last)[moved]
    return ForecastMetrics(
        n=len(samples),
        mae_model=mae_model,
        mae_naive=mae_naive,
        mae_ratio=mae_model / mae_naive if mae_naive > 0 else float("nan"),
        direction_n=int(moved.sum()),
        direction_hit_rate=float(hits.mean()) if hits.size else float("nan"),
        coverage=float(np.mean((actual >= lower) & (actual <= upper))),
        mean_width=float(np.mean((upper - lower) / last)),
    )


def max_drawdown(equity: list[float]) -> float:
    """Largest peak-to-trough loss as a fraction of the peak (0.05 means -5%)."""
    values = np.array(equity)
    peaks = np.maximum.accumulate(values)
    return float(np.max((peaks - values) / peaks)) if values.size else 0.0


def buy_and_hold_curve(
    prices: list[dict[str, float]], symbols: list[str], capital: float, invested_share: float
) -> list[float | None]:
    """Equal-weight reference: bought once at the first cycle where every symbol has a price.

    Only `invested_share` of the capital is invested, the rest stays in cash, so the reference
    carries the same exposure as the agent. Fractional quantities, no rebalancing, no costs.
    A cycle missing a price stays empty.
    """
    cash = capital * (1 - invested_share)
    units: dict[str, float] | None = None
    curve: list[float | None] = []
    for cycle_prices in prices:
        if any(symbol not in cycle_prices for symbol in symbols):
            curve.append(None)
            continue
        if units is None:
            units = {s: capital * invested_share / len(symbols) / cycle_prices[s] for s in symbols}
        curve.append(cash + sum(units[s] * cycle_prices[s] for s in symbols))
    return curve
