from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent import cycle as cycle_module
from agent.broker import OrderRecord
from agent.config import Config, load_config
from agent.cycle import Cycle
from agent.data import DataError
from agent.forecast import PriceForecast
from agent.llm import Decision, Decisions, ForecastTool, LlmError, SymbolDecision
from agent.macro import MacroError
from agent.risk import OrderSpec, Position
from agent.store import Store

START_EQUITY = 100_000.0


class FakeBroker:
    def __init__(self, equity: float = START_EQUITY) -> None:
        self.equity = equity
        self.submitted: list[str] = []

    def is_market_open(self) -> bool:
        return True

    def get_equity(self) -> float:
        return self.equity

    def get_positions(self) -> dict[str, Position]:
        return {}

    def refresh_order(self, record: OrderRecord) -> OrderRecord:
        return record.model_copy(
            update={"status": "filled", "filled_qty": 1.0, "filled_avg_price": 100.5}
        )

    def submit_order(self, spec: OrderSpec, client_order_id: str) -> OrderRecord:
        self.submitted.append(client_order_id)
        return OrderRecord(
            order_id="o1",
            client_order_id=client_order_id,
            symbol=spec.symbol,
            side=spec.side,
            status="accepted",
            notional=spec.notional,
        )


@pytest.fixture
def config() -> Config:
    base = load_config()
    return base.model_copy(update={"market": base.market.model_copy(update={"symbols": ["SPY"]})})


@pytest.fixture
def llm_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_forecast(self: Cycle, symbol: str) -> PriceForecast:
        return PriceForecast(
            symbol=symbol,
            model="m",
            last_bar_start=datetime(2026, 11, 10, tzinfo=UTC),
            last_price=100.0,
            median=[101.0],
            lower=[99.0],
            upper=[103.0],
            uncertainty=0.02,
        )

    def fake_decide(
        client: object, symbols: list[str], data: str, tool: ForecastTool, *rest: object
    ) -> Decisions:
        calls.append("llm")
        decision = Decision(action="buy", confidence=0.9, size_fraction=1.0, rationale="test")
        served = [symbol for symbol in symbols if tool(symbol) is not None]
        return Decisions(decisions=[SymbolDecision(symbol=s, decision=decision) for s in served])

    monkeypatch.setattr(Cycle, "_forecast", fake_forecast)
    monkeypatch.setattr(cycle_module, "decide", fake_decide)
    return calls


def make_cycle(
    config: Config, tmp_path: Path, broker: FakeBroker, execute: bool, cycle_id: str = "c1"
) -> Cycle:
    store = Store(tmp_path / "j.db")
    return Cycle(config, broker, None, store, cycle_id, execute, False, "key")  # type: ignore[arg-type]


def test_rerun_never_duplicates_order_nor_llm_call(
    config: Config, tmp_path: Path, llm_calls: list[str]
) -> None:
    broker = FakeBroker()
    make_cycle(config, tmp_path, broker, True).run()
    report = make_cycle(config, tmp_path, broker, True).run()
    assert broker.submitted == ["c1-SPY-buy"]
    assert llm_calls == ["llm"]
    assert report.outcomes["SPY"].order is not None


def test_account_equity_is_journaled(config: Config, tmp_path: Path, llm_calls: list[str]) -> None:
    make_cycle(config, tmp_path, FakeBroker(), False).run()
    assert Store(tmp_path / "j.db").get_state(cycle_module.ACCOUNT_EQUITY_KEY) == str(START_EQUITY)


def test_simulation_sends_no_order(config: Config, tmp_path: Path, llm_calls: list[str]) -> None:
    broker = FakeBroker()
    report = make_cycle(config, tmp_path, broker, False).run()
    assert broker.submitted == []
    verdict = report.outcomes["SPY"].verdict
    assert verdict is not None and verdict.approved


def test_below_capital_floor_halts_and_stays_halted(
    config: Config, tmp_path: Path, llm_calls: list[str]
) -> None:
    broker = FakeBroker()
    make_cycle(config, tmp_path, broker, True, "c0").run()
    broker.submitted.clear()
    below_floor = config.risk.allocated_capital - config.risk.capital_floor + 500.0
    broker.equity = START_EQUITY - below_floor
    report = make_cycle(config, tmp_path, broker, True, "c2").run()
    assert report.halted_reason is not None and broker.submitted == []
    broker.equity = START_EQUITY
    report = make_cycle(config, tmp_path, broker, True, "c3").run()
    assert report.halted_reason is not None and broker.submitted == []
    Store(tmp_path / "j.db").delete_state(cycle_module.HALTED_KEY)
    report = make_cycle(config, tmp_path, broker, True, "c4").run()
    assert report.halted_reason is None and broker.submitted == ["c4-SPY-buy"]


def test_fill_is_recorded_after_the_order_and_only_when_executing(
    config: Config, tmp_path: Path, llm_calls: list[str]
) -> None:
    make_cycle(config, tmp_path, FakeBroker(), True).run()
    stored = Store(tmp_path / "j.db").list_steps("order")
    assert len(stored) == 1
    record = OrderRecord.model_validate_json(stored[0].result)
    assert record.status == "filled" and record.filled_avg_price == 100.5


def test_a_symbol_without_forecast_does_not_stop_the_others(
    config: Config, tmp_path: Path, llm_calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Cycle._forecast

    def forecast_or_fail(self: Cycle, symbol: str) -> PriceForecast:
        if symbol == "QQQ":
            raise DataError("QQQ: no data")
        return original(self, symbol)

    monkeypatch.setattr(Cycle, "_forecast", forecast_or_fail)
    two = config.model_copy(
        update={"market": config.market.model_copy(update={"symbols": ["SPY", "QQQ"]})}
    )
    broker = FakeBroker()
    report = make_cycle(two, tmp_path, broker, True).run()
    assert broker.submitted == ["c1-SPY-buy"]
    assert (
        report.outcomes["QQQ"].error == "QQQ: no data" and report.outcomes["QQQ"].decision is None
    )
    assert report.status == "error"


def test_macro_failure_gives_no_forecast_and_no_order(
    config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_macro(*args: object) -> None:
        raise MacroError("vix: FRED request failed (HTTP 503)")

    def decide_with_tool(
        client: object, symbols: list[str], data: str, tool: ForecastTool, *rest: object
    ) -> Decisions:
        assert all(tool(symbol) is None for symbol in symbols)
        raise LlmError("no forecast served")

    broker = FakeBroker()
    broker.fetch_hourly_bars = lambda *args: []  # type: ignore[attr-defined]
    monkeypatch.setattr(cycle_module, "fetch_macro", failing_macro)
    monkeypatch.setattr(cycle_module, "load_model", lambda name: object())
    monkeypatch.setattr(cycle_module, "decide", decide_with_tool)
    report = make_cycle(config, tmp_path, broker, True).run()
    assert report.status == "error" and broker.submitted == []
    assert report.outcomes["SPY"].forecast is None
    assert "FRED" in str(report.outcomes["SPY"].error)
