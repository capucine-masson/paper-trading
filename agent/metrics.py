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
