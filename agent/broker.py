"""The only module talking to Alpaca (paper account only)."""

import logging
from datetime import datetime

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from pydantic import BaseModel

from agent.config import Secrets

logger = logging.getLogger(__name__)

PAPER_URL = "https://paper-api.alpaca.markets"
PAPER_ACCOUNT_PREFIX = "PA"


class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    close: float


class Broker:
    def __init__(self, secrets: Secrets, feed: str) -> None:
        key = secrets.alpaca_api_key.get_secret_value()
        secret = secrets.alpaca_secret_key.get_secret_value()
        self._trading = TradingClient(key, secret, paper=True, url_override=PAPER_URL)
        self._data = StockHistoricalDataClient(key, secret)
        self._feed = DataFeed(feed)
        self._check_paper_account()

    def _check_paper_account(self) -> None:
        number = str(self._trading.get_account().account_number)  # type: ignore[union-attr]
        if not number.startswith(PAPER_ACCOUNT_PREFIX):
            raise RuntimeError("Refusing to start: the Alpaca account is not a paper account.")

    def is_market_open(self) -> bool:
        return bool(self._trading.get_clock().is_open)  # type: ignore[union-attr]

    def fetch_hourly_bars(self, symbols: list[str], start: datetime, end: datetime) -> list[Bar]:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Hour,
            start=start,
            end=end,
            feed=self._feed,
        )
        bar_set = self._data.get_stock_bars(request)
        return [
            Bar(symbol=symbol, timestamp=bar.timestamp, close=bar.close)
            for symbol, bars in bar_set.data.items()  # type: ignore[union-attr]
            for bar in bars
        ]
