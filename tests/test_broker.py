from types import SimpleNamespace

import pytest
from alpaca.common.exceptions import APIError

from agent.broker import Broker, BrokerError
from agent.config import BrokerConfig
from agent.risk import OrderSpec

SPEC = OrderSpec(symbol="SPY", side="buy", notional=100.0)


def fake_order(client_order_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="o1",
        client_order_id=client_order_id,
        symbol="SPY",
        side=SimpleNamespace(value="buy"),
        status=SimpleNamespace(value="accepted"),
        notional="100",
        qty=None,
    )


class NotFound(APIError):
    @property
    def status_code(self) -> int:
        return 404


class FakeTrading:
    def __init__(self, existing: bool = False, failures: int = 0) -> None:
        self.existing = existing
        self.failures = failures
        self.submits = 0

    def get_order_by_client_id(self, client_order_id: str) -> SimpleNamespace:
        if self.existing:
            return fake_order(client_order_id)
        raise NotFound("not found")  # type: ignore[no-untyped-call]

    def submit_order(self, request: object) -> SimpleNamespace:
        self.submits += 1
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("timeout")
        self.existing = True
        return fake_order("id1")


def make_broker(trading: FakeTrading, attempts: int = 3) -> Broker:
    broker = Broker.__new__(Broker)
    broker._config = BrokerConfig(max_attempts=attempts, retry_delay_s=0.001)
    broker._trading = trading  # type: ignore[assignment]
    return broker


def test_existing_order_is_returned_without_resubmitting() -> None:
    trading = FakeTrading(existing=True)
    record = make_broker(trading).submit_order(SPEC, "id1")
    assert record.client_order_id == "id1" and trading.submits == 0


def test_timeout_is_retried_after_lookup() -> None:
    trading = FakeTrading(failures=1)
    make_broker(trading).submit_order(SPEC, "id1")
    assert trading.submits == 2


def test_gives_up_after_max_attempts() -> None:
    trading = FakeTrading(failures=5)
    with pytest.raises(BrokerError):
        make_broker(trading, attempts=2).submit_order(SPEC, "id1")
    assert trading.submits == 2
