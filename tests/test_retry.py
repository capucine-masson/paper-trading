from collections.abc import Callable

import pytest

from agent.retry import is_transient_status, retry


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr("agent.retry.time.sleep", sleeps.append)
    return sleeps


def flaky(failures: int) -> tuple[list[int], Callable[[], str]]:
    calls: list[int] = []

    def action() -> str:
        calls.append(1)
        if len(calls) <= failures:
            raise ConnectionError("down")
        return "ok"

    return calls, action


def test_status_429_and_5xx_are_transient_but_other_statuses_are_not() -> None:
    assert is_transient_status(429)
    assert is_transient_status(503)
    assert not is_transient_status(404)


def test_transient_error_is_retried_with_a_doubling_delay(no_sleep: list[float]) -> None:
    calls, action = flaky(2)
    result = retry(action, (ConnectionError,), lambda e: True, max_attempts=3, delay_s=1.0)
    assert result == "ok"
    assert len(calls) == 3
    assert no_sleep == [1.0, 2.0]


def test_last_attempt_raises_the_error() -> None:
    calls, action = flaky(5)
    with pytest.raises(ConnectionError):
        retry(action, (ConnectionError,), lambda e: True, max_attempts=2, delay_s=0.1)
    assert len(calls) == 2


def test_non_transient_error_is_not_retried() -> None:
    calls, action = flaky(5)
    with pytest.raises(ConnectionError):
        retry(action, (ConnectionError,), lambda e: False, max_attempts=3, delay_s=0.1)
    assert len(calls) == 1
