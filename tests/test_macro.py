import time
from datetime import UTC, date, datetime, timedelta

import httpx
import numpy as np
import pytest

from agent.config import MacroConfig, load_config
from agent.macro import MacroData, MacroError, Observation, fetch_macro, macro_covariates

CONFIG = load_config().macro
START = datetime(2026, 11, 1, tzinfo=UTC)
END = datetime(2026, 11, 15, tzinfo=UTC)
DATA = MacroData(
    series={
        "vix": [
            Observation(date=date(2026, 11, 9), value=20.0),
            Observation(date=date(2026, 11, 10), value=25.0),
        ]
    }
)


def test_value_is_visible_only_the_day_after_it_is_published() -> None:
    day = datetime(2026, 11, 10, tzinfo=UTC)
    bars = [day - timedelta(hours=1), day, day + timedelta(hours=23), day + timedelta(hours=24)]
    result = macro_covariates(DATA, bars)
    np.testing.assert_array_equal(result, [[np.nan, 20.0, 20.0, 25.0]])


def test_bar_before_the_first_observation_is_nan() -> None:
    result = macro_covariates(DATA, [datetime(2026, 11, 9, 12, tzinfo=UTC)])
    assert np.isnan(result).all()


REAL_CLIENT = httpx.Client


def fred_client(handler: httpx.MockTransport) -> httpx.Client:
    return REAL_CLIENT(transport=handler)


def test_missing_values_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "observations": [
            {"date": "2026-11-09", "value": "."},
            {"date": "2026-11-10", "value": "4.1"},
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    monkeypatch.setattr(httpx, "Client", lambda timeout: fred_client(transport))
    config = MacroConfig(**{**CONFIG.model_dump(), "series": {"us10y": "DGS10"}})
    result = fetch_macro(config, "key", START, END)
    assert result.series["us10y"] == [Observation(date=date(2026, 11, 10), value=4.1)]


def test_client_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400)

    monkeypatch.setattr(httpx, "Client", lambda timeout: fred_client(httpx.MockTransport(handler)))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with pytest.raises(MacroError, match="HTTP 400") as error:
        fetch_macro(CONFIG, "secret-key", START, END)
    assert len(calls) == 1 and "secret-key" not in str(error.value)


def test_server_error_is_retried_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "Client", lambda timeout: fred_client(httpx.MockTransport(handler)))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with pytest.raises(MacroError):
        fetch_macro(CONFIG, "key", START, END)
    assert len(calls) == CONFIG.max_attempts
