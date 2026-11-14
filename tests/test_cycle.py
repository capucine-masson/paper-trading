from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent import cycle as cycle_module
from agent.broker import OrderRecord
from agent.config import Config, load_config
from agent.cycle import Cycle
from agent.forecast import PriceForecast
from agent.llm import Decision
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

    def fake_decide(*args: object) -> Decision:
        calls.append("llm")
        return Decision(action="buy", confidence=0.9, rationale="test")

    monkeypatch.setattr(Cycle, "_forecast", fake_forecast)
    monkeypatch.setattr(cycle_module, "decide", fake_decide)
    return calls


def make_cycle(
    config: Config, tmp_path: Path, broker: FakeBroker, execute: bool, cycle_id: str = "c1"
) -> Cycle:
    store = Store(tmp_path / "j.db")
    return Cycle(config, broker, None, store, cycle_id, execute, False)  # type: ignore[arg-type]


def test_rerun_never_duplicates_order_nor_llm_call(
    config: Config, tmp_path: Path, llm_calls: list[str]
) -> None:
    broker = FakeBroker()
    make_cycle(config, tmp_path, broker, True).run()
    report = make_cycle(config, tmp_path, broker, True).run()
    assert broker.submitted == ["c1-SPY-buy"]
    assert llm_calls == ["llm"]
    assert report.outcomes["SPY"].order is not None


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
    broker.equity = START_EQUITY - 2_500.0
    report = make_cycle(config, tmp_path, broker, True, "c2").run()
    assert report.halted_reason is not None and broker.submitted == []
    broker.equity = START_EQUITY
    report = make_cycle(config, tmp_path, broker, True, "c3").run()
    assert report.halted_reason is not None and broker.submitted == []
    Store(tmp_path / "j.db").delete_state(cycle_module.HALTED_KEY)
    report = make_cycle(config, tmp_path, broker, True, "c4").run()
    assert report.halted_reason is None and broker.submitted == ["c4-SPY-buy"]
