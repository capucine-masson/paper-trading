"""Daily macro drivers from FRED, aligned on hourly bars without look-ahead."""

import logging
import time
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta

import httpx
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from agent.config import MacroConfig

logger = logging.getLogger(__name__)

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_MISSING_VALUE = "."
PUBLICATION_LAG = timedelta(days=1)
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500


class MacroError(Exception):
    """Raised when the macro drivers cannot be fetched or trusted; the cycle gets no forecast."""


class RawObservation(BaseModel):
    date: date
    value: str


class FredResponse(BaseModel):
    observations: list[RawObservation]


class Observation(BaseModel):
    date: date
    value: float


class MacroData(BaseModel):
    series: dict[str, list[Observation]]


def fetch_macro(config: MacroConfig, api_key: str, start: datetime, end: datetime) -> MacroData:
    with httpx.Client(timeout=config.timeout_s) as client:
        series = {
            name: _fetch_series(client, config, api_key, name, fred_id, start, end)
            for name, fred_id in config.series.items()
        }
    return MacroData(series=series)


def _fetch_series(
    client: httpx.Client,
    config: MacroConfig,
    api_key: str,
    name: str,
    fred_id: str,
    start: datetime,
    end: datetime,
) -> list[Observation]:
    params = {
        "series_id": fred_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.date().isoformat(),
        "observation_end": end.date().isoformat(),
    }
    payload = _get_with_retries(client, config, name, params)
    observations = [
        Observation(date=item.date, value=float(item.value))
        for item in FredResponse.model_validate_json(payload).observations
        if item.value != FRED_MISSING_VALUE
    ]
    if not observations:
        raise MacroError(f"{name}: FRED returned no observation")
    return observations


def _get_with_retries(
    client: httpx.Client, config: MacroConfig, name: str, params: dict[str, str]
) -> bytes:
    """Retry only transient errors (network, 429, 5xx); the key never reaches the logs."""
    delay = config.retry_delay_s
    attempt = 1
    while True:
        try:
            response = client.get(FRED_URL, params=params)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            transient = status == HTTP_TOO_MANY_REQUESTS or status >= HTTP_SERVER_ERROR
            reason = f"HTTP {status}"
        except httpx.TransportError as error:
            transient, reason = True, type(error).__name__
        if not transient or attempt >= config.max_attempts:
            raise MacroError(f"{name}: FRED request failed ({reason})")
        logger.warning("transient FRED error on %s (%s), retrying in %.1fs", name, reason, delay)
        time.sleep(delay)
        delay *= 2
        attempt += 1


def macro_covariates(data: MacroData, bar_starts: list[datetime]) -> NDArray[np.float64]:
    """Shape (n_series, n_bars): the latest value published before each bar, NaN before the first.

    A daily value is only visible from the next day 00:00 UTC, so no bar sees a value that was
    not yet public.
    """
    rows = []
    for observations in data.series.values():
        visible_from = [
            datetime(o.date.year, o.date.month, o.date.day, tzinfo=UTC) + PUBLICATION_LAG
            for o in observations
        ]
        rows.append(
            [
                observations[i - 1].value if (i := bisect_right(visible_from, start)) else np.nan
                for start in bar_starts
            ]
        )
    return np.array(rows, dtype=np.float64)
