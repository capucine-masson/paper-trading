"""The only module talking to Alpaca (paper account only)."""

import logging
from collections.abc import Callable
from datetime import datetime

from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.models.bars import BarSet
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.models import Clock, Order, TradeAccount
from alpaca.trading.models import Position as AlpacaPosition
from alpaca.trading.requests import MarketOrderRequest
from pydantic import BaseModel
from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter

from agent.config import BrokerConfig, Secrets
from agent.data import Bar
from agent.retry import is_transient_status, retry
from agent.risk import OrderSpec, Position

logger = logging.getLogger(__name__)

PAPER_URL = "https://paper-api.alpaca.markets"
PAPER_ACCOUNT_PREFIX = "PA"
HTTP_NOT_FOUND = 404


class BrokerError(Exception):
    """Raised when Alpaca cannot be reached or refuses a request."""


class OrderRecord(BaseModel):
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    status: str
    notional: float | None = None
    qty: float | None = None
    filled_qty: float | None = None
    filled_avg_price: float | None = None
    filled_at: datetime | None = None


def _expect[T](response: object, kind: type[T]) -> T:
    """Alpaca types its answers as model-or-dict; only the model is ever expected here."""
    if not isinstance(response, kind):
        raise BrokerError(f"Unexpected Alpaca response: {type(response).__name__}")
    return response


def _is_transient(error: Exception) -> bool:
    if isinstance(error, APIError):
        status: int = error.status_code
        return is_transient_status(status)
    return True


class TimeoutAdapter(HTTPAdapter):
    """alpaca-py sets no timeout on its requests; every call through this adapter gets one."""

    def __init__(self, timeout_s: float) -> None:
        super().__init__()
        self._timeout_s = timeout_s

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float | None, float | None] | None = None,
        verify: bool | str = True,
        cert: str | tuple[str, str] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> Response:
        return super().send(
            request, stream, self._timeout_s if timeout is None else timeout, verify, cert, proxies
        )


def _with_timeout(client: TradingClient | StockHistoricalDataClient, timeout_s: float) -> None:
    client._session.mount("https://", TimeoutAdapter(timeout_s))


class Broker:
    def __init__(self, secrets: Secrets, feed: str, config: BrokerConfig) -> None:
        key = secrets.alpaca_api_key.get_secret_value()
        secret = secrets.alpaca_secret_key.get_secret_value()
        self._config = config
        self._trading = TradingClient(key, secret, paper=True, url_override=PAPER_URL)
        self._data = StockHistoricalDataClient(key, secret)
        _with_timeout(self._trading, config.timeout_s)
        _with_timeout(self._data, config.timeout_s)
        self._feed = DataFeed(feed)
        self._check_paper_account()

    def _retry[T](self, action: Callable[[], T]) -> T:
        """Retry only transient errors (network, 429, 5xx), with an increasing delay."""
        try:
            return retry(
                action,
                (APIError, OSError),
                _is_transient,
                self._config.max_attempts,
                self._config.retry_delay_s,
            )
        except (APIError, OSError) as error:
            raise BrokerError(f"Alpaca request failed: {error}") from error

    def _check_paper_account(self) -> None:
        account = _expect(self._retry(self._trading.get_account), TradeAccount)
        if not str(account.account_number).startswith(PAPER_ACCOUNT_PREFIX):
            raise RuntimeError("Refusing to start: the Alpaca account is not a paper account.")

    def is_market_open(self) -> bool:
        return bool(_expect(self._retry(self._trading.get_clock), Clock).is_open)

    def get_equity(self) -> float:
        equity = _expect(self._retry(self._trading.get_account), TradeAccount).equity
        if equity is None:
            raise BrokerError("Alpaca returned no account equity")
        return float(equity)

    def get_positions(self) -> dict[str, Position]:
        positions = self._retry(self._trading.get_all_positions)
        checked = [_expect(p, AlpacaPosition) for p in positions]
        return {
            p.symbol: Position(qty=float(p.qty), market_value=float(p.market_value or 0.0))
            for p in checked
        }

    def fetch_hourly_bars(self, symbols: list[str], start: datetime, end: datetime) -> list[Bar]:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Hour,
            start=start,
            end=end,
            feed=self._feed,
        )
        bar_set = _expect(self._retry(lambda: self._data.get_stock_bars(request)), BarSet)
        return [
            Bar(symbol=symbol, timestamp=bar.timestamp, close=bar.close)
            for symbol, bars in bar_set.data.items()
            for bar in bars
        ]

    def find_order(self, client_order_id: str) -> OrderRecord | None:
        try:
            order = self._trading.get_order_by_client_id(client_order_id)
        except APIError as error:
            if error.status_code == HTTP_NOT_FOUND:
                return None
            raise
        return _to_record(_expect(order, Order))

    def refresh_order(self, record: OrderRecord) -> OrderRecord:
        """Read the order again (status and fill) without ever submitting anything."""
        latest = self._retry(lambda: self.find_order(record.client_order_id))
        return record if latest is None else latest

    def submit_order(self, spec: OrderSpec, client_order_id: str) -> OrderRecord:
        """Look the order up by client_order_id before each attempt: never a duplicate."""
        request = MarketOrderRequest(
            symbol=spec.symbol,
            side=OrderSide(spec.side),
            time_in_force=TimeInForce.DAY,
            notional=spec.notional,
            qty=spec.qty,
            client_order_id=client_order_id,
        )

        def attempt() -> OrderRecord:
            existing = self.find_order(client_order_id)
            if existing is not None:
                return existing
            return _to_record(_expect(self._trading.submit_order(request), Order))

        return self._retry(attempt)


def _to_record(order: Order) -> OrderRecord:
    if order.side is None:
        raise BrokerError(f"Alpaca order {order.client_order_id} has no side")
    return OrderRecord(
        order_id=str(order.id),
        client_order_id=str(order.client_order_id),
        symbol=str(order.symbol),
        side=order.side.value,
        status=order.status.value,
        notional=_number(order.notional),
        qty=_number(order.qty),
        filled_qty=_number(order.filled_qty),
        filled_avg_price=_number(order.filled_avg_price),
        filled_at=order.filled_at,
    )


def _number(value: str | float | None) -> float | None:
    return None if value is None else float(value)
