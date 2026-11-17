from datetime import UTC, datetime

import pytest
import requests
from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.client import TradingClient
from alpaca.trading.models import Order

from agent.broker import Broker, BrokerError, TimeoutAdapter, _with_timeout
from agent.config import BrokerConfig
from agent.risk import OrderSpec

NOW = datetime(2026, 11, 10, tzinfo=UTC)
SPEC = OrderSpec(symbol="SPY", side="buy", notional=100.0)


def fake_order(client_order_id: str) -> Order:
    return Order.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "client_order_id": client_order_id,
            "created_at": NOW,
            "updated_at": NOW,
            "submitted_at": NOW,
            "order_class": "simple",
            "time_in_force": "day",
            "status": "accepted",
            "extended_hours": False,
            "symbol": "SPY",
            "side": "buy",
            "notional": "100",
        }
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

    def get_order_by_client_id(self, client_order_id: str) -> Order:
        if self.existing:
            return fake_order(client_order_id)
        raise NotFound("not found")  # type: ignore[no-untyped-call]

    def submit_order(self, request: object) -> Order:
        self.submits += 1
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("timeout")
        self.existing = True
        return fake_order("id1")


def make_broker(trading: FakeTrading, attempts: int = 3) -> Broker:
    broker = Broker.__new__(Broker)
    broker._config = BrokerConfig(
        timeout_s=5,
        max_attempts=attempts,
        retry_delay_s=0.001,
        fill_check_attempts=1,
        fill_check_interval_s=0.001,
    )
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


def test_adapter_applies_its_timeout_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    def fake_send(self: object, request: object, stream: bool, timeout: object, *_: object) -> None:
        seen.append(timeout)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_send)
    adapter = TimeoutAdapter(7)
    prepared = requests.Request("GET", "https://example.test").prepare()
    adapter.send(prepared)
    adapter.send(prepared, timeout=3)
    assert seen == [7, 3]


def test_alpaca_clients_use_the_timeout_adapter() -> None:
    """Fails if an alpaca-py upgrade changes the session the timeout relies on."""
    for client in (TradingClient("k", "s", paper=True), StockHistoricalDataClient("k", "s")):
        _with_timeout(client, 7)
        adapter = client._session.get_adapter("https://paper-api.alpaca.markets")
        assert isinstance(adapter, TimeoutAdapter)
