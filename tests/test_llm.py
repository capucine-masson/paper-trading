from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from agent.config import LlmConfig
from agent.forecast import PriceForecast
from agent.llm import Decision, LlmError, build_user_prompt, decide

CONFIG = LlmConfig(
    model="test-model", temperature=0.2, timeout_s=5, max_attempts=2, retry_delay_s=0.001
)
FORECAST = PriceForecast(
    symbol="SPY",
    model="m",
    last_price=100.0,
    median=[101.0],
    lower=[99.0],
    upper=[103.0],
    uncertainty=0.04,
)
GOOD = Decision(action="buy", confidence=0.7, rationale="Median is above the last price.")


class FakeMessage:
    def __init__(self, parsed: Decision | None) -> None:
        self.parsed = parsed


class FakeChoice:
    def __init__(self, parsed: Decision | None) -> None:
        self.message = FakeMessage(parsed)


class FakeResponse:
    def __init__(self, parsed: Decision | None) -> None:
        self.choices = [FakeChoice(parsed)]


class FakeChat:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def parse(self, **_: Any) -> FakeResponse:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


class FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.chat = FakeChat(outcomes)


def run(outcomes: list[Any]) -> tuple[Decision, FakeClient]:
    client = FakeClient(outcomes)
    return decide(client, FORECAST, CONFIG, "c1"), client  # type: ignore[arg-type]


def test_valid_decision() -> None:
    decision, client = run([GOOD])
    assert decision.action == "buy"
    assert client.chat.calls == 1


def test_invalid_output_is_retried_once() -> None:
    decision, client = run([None, GOOD])
    assert decision == GOOD
    assert client.chat.calls == 2


def test_invalid_twice_is_rejected() -> None:
    client = FakeClient([None, None])
    with pytest.raises(LlmError):
        decide(client, FORECAST, CONFIG, "c1")  # type: ignore[arg-type]


def test_transient_error_is_retried() -> None:
    decision, client = run([httpx.ConnectError("boom"), GOOD])
    assert decision == GOOD
    assert client.chat.calls == 2


def test_transient_error_gives_up() -> None:
    client = FakeClient([httpx.ConnectError("boom")] * 2)
    with pytest.raises(LlmError):
        decide(client, FORECAST, CONFIG, "c1")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "short", "confidence": 0.5, "rationale": "x"},
        {"action": "buy", "confidence": 1.5, "rationale": "x"},
        {"action": "buy", "confidence": 0.5, "rationale": ""},
    ],
)
def test_decision_schema_rejects_absurd_output(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Decision.model_validate(payload)


def test_prompt_contains_computed_return_and_delimiters() -> None:
    prompt = build_user_prompt(FORECAST)
    assert "<forecast_data>" in prompt and "+1.0000%" in prompt
