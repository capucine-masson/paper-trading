import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from mistralai.client import Mistral
from mistralai.client.models import FunctionCall, ToolCall
from pydantic import ValidationError

from agent.config import LlmConfig
from agent.forecast import PriceForecast
from agent.llm import (
    FORECAST_TOOL_NAME,
    Decision,
    Decisions,
    LlmError,
    SymbolDecision,
    build_forecast_data,
    build_portfolio_data,
    decide,
)

CONFIG = LlmConfig(
    model="test-model",
    temperature=0.2,
    timeout_s=5,
    max_attempts=2,
    retry_delay_s=0.001,
)
SYMBOLS = ["SPY", "QQQ"]
GOOD = Decision(
    action="buy", size_fraction=0.5, rationale="The expected move is positive."
)


def forecast(symbol: str) -> PriceForecast:
    return PriceForecast(
        symbol=symbol,
        model="m",
        last_bar_start=datetime(2026, 11, 10, tzinfo=UTC),
        last_price=100.0,
        median=[101.0],
        lower=[99.0],
        upper=[103.0],
        uncertainty=0.04,
        signal_strength=0.4,
    )


def decisions(*symbols: str) -> Decisions:
    return Decisions(decisions=[SymbolDecision(symbol=s, decision=GOOD) for s in symbols])


def tool_call(symbol: str, name: str = FORECAST_TOOL_NAME, call_id: str = "c") -> ToolCall:
    arguments = json.dumps({"symbol": symbol})
    return ToolCall(id=call_id, function=FunctionCall(name=name, arguments=arguments))


class FakeChat:
    """`complete` answers with the given tool calls, `parse` with the given outcomes in order."""

    def __init__(self, outcomes: list[Any], calls: list[ToolCall]) -> None:
        self.outcomes = outcomes
        self.calls = calls
        self.parses = 0

    def complete(self, **_: Any) -> SimpleNamespace:
        message = SimpleNamespace(content="", tool_calls=self.calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def parse(self, **_: Any) -> SimpleNamespace:
        outcome = self.outcomes[self.parses]
        self.parses += 1
        if isinstance(outcome, Exception):
            raise outcome
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        message = SimpleNamespace(parsed=outcome)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def run(
    outcomes: list[Any],
    calls: list[ToolCall] | None = None,
    available: tuple[str, ...] = ("SPY", "QQQ"),
) -> tuple[Decisions, FakeChat]:
    chat = FakeChat(
        outcomes, [tool_call(s, call_id=s) for s in SYMBOLS] if calls is None else calls
    )
    client = cast(Mistral, SimpleNamespace(chat=chat))
    served = {s: forecast(s) for s in available}
    return decide(client, SYMBOLS, "data", served.get, CONFIG, "c1"), chat


def test_valid_decisions_for_every_forecast_symbol() -> None:
    result, chat = run([decisions("SPY", "QQQ")])
    assert {d.symbol for d in result.decisions} == {"SPY", "QQQ"} and chat.parses == 1


def test_the_code_runs_the_forecast_tool() -> None:
    requested: list[str] = []

    def spy(symbol: str) -> PriceForecast:
        requested.append(symbol)
        return forecast(symbol)

    chat = FakeChat([decisions("SPY", "QQQ")], [tool_call("SPY", call_id="a"), tool_call("QQQ")])
    decide(cast(Mistral, SimpleNamespace(chat=chat)), SYMBOLS, "data", spy, CONFIG, "c1")
    assert requested == ["SPY", "QQQ"]


def test_symbol_without_forecast_gets_no_decision() -> None:
    result, _ = run([decisions("SPY")], available=("SPY",))
    assert [d.symbol for d in result.decisions] == ["SPY"]


def test_decision_for_a_symbol_without_forecast_is_dropped() -> None:
    result, chat = run([decisions("SPY", "QQQ")], available=("SPY",))
    assert [d.symbol for d in result.decisions] == ["SPY"] and chat.parses == 1


def test_invalid_output_is_retried_once() -> None:
    result, chat = run([None, decisions("SPY", "QQQ")])
    assert len(result.decisions) == 2 and chat.parses == 2


@pytest.mark.parametrize(
    "answer",
    [
        None,
        decisions("SPY"),  # QQQ is missing
        decisions("SPY", "SPY", "QQQ"),  # SPY twice
    ],
)
def test_output_that_does_not_cover_the_forecast_symbols_is_rejected(answer: Decisions) -> None:
    with pytest.raises(LlmError):
        run([answer, answer])


def test_transient_error_is_retried() -> None:
    result, chat = run([httpx.ConnectError("boom"), decisions("SPY", "QQQ")])
    assert len(result.decisions) == 2 and chat.parses == 2


def test_transient_error_gives_up() -> None:
    with pytest.raises(LlmError):
        run([httpx.ConnectError("boom")] * 2)


def test_bad_tool_calls_get_an_error_text_and_valid_ones_are_served() -> None:
    calls = [tool_call("TSLA", call_id="a"), tool_call("SPY", "other_tool", "b"), tool_call("SPY")]
    result, _ = run([decisions("SPY")], calls=calls, available=("SPY",))
    assert [d.symbol for d in result.decisions] == ["SPY"]


@pytest.mark.parametrize("calls", [[], [tool_call("TSLA")], [tool_call("SPY", "other_tool")]])
def test_no_valid_tool_call_gives_no_decision(calls: list[ToolCall]) -> None:
    with pytest.raises(LlmError):
        run([decisions("SPY")], calls=calls)


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "short", "size_fraction": 0.5, "rationale": "x"},
        {"action": "buy", "size_fraction": 1.5, "rationale": "x"},
        {"action": "buy", "rationale": "x"},
        {"action": "buy", "size_fraction": 0.5, "rationale": ""},
    ],
)
def test_decision_schema_rejects_absurd_output(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Decision.model_validate(payload)


def test_forecast_data_has_the_computed_return_the_signal_strength_and_delimiters() -> None:
    data = build_forecast_data(forecast("SPY"))
    assert "<forecast_data>" in data and "expected_return_median: +1.0000%" in data
    assert "signal_strength_0_to_1: 0.40" in data


def test_portfolio_data_gives_cash_positions_and_results() -> None:
    data = build_portfolio_data(10_500.0, 10_000.0, 10_000.0, {"SPY": 1_500.0})
    assert "cash_usd: 9,000.00" in data and "return_since_start: +5.00%" in data
    assert "positions: SPY $1,500.00" in data
    assert "positions: none" in build_portfolio_data(10_000.0, 10_000.0, 10_000.0, {})
