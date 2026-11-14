"""One cycle: data, forecast, LLM, risk, order. Every external action is a resumable step."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from mistralai.client import Mistral
from pydantic import BaseModel
from timestral import TimestralForecaster

from agent.broker import Broker, BrokerError, OrderRecord
from agent.config import Config
from agent.data import Bar, DataError, build_series, check_freshness
from agent.forecast import ForecastError, PriceForecast, forecast_symbol, load_model
from agent.llm import Decision, LlmError, decide
from agent.risk import (
    Portfolio,
    PortfolioSnapshot,
    Position,
    Verdict,
    evaluate,
    halt_reason,
    snapshot,
)
from agent.store import CYCLE_SCOPE, Store

logger = logging.getLogger(__name__)

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"
BASELINE_KEY = "baseline_equity"
HALTED_KEY = "halted_reason"
DAY_START_KEY = "day_start_equity:"


class SymbolOutcome(BaseModel):
    forecast: PriceForecast | None = None
    decision: Decision | None = None
    verdict: Verdict | None = None
    order: OrderRecord | None = None
    error: str | None = None


class CycleReport(BaseModel):
    status: str
    detail: str
    halted_reason: str | None = None
    outcomes: dict[str, SymbolOutcome] = {}


@dataclass
class Cycle:
    config: Config
    broker: Broker
    llm_client: Mistral
    store: Store
    cycle_id: str
    execute: bool
    ignore_market_clock: bool
    _inputs: tuple[list[Bar], TimestralForecaster, datetime] | None = field(
        default=None, init=False
    )

    def run(self) -> CycleReport:
        self.store.start_cycle(self.cycle_id)
        if self.ignore_market_clock:
            logger.warning(
                "cycle %s: market clock and data freshness checks ignored", self.cycle_id
            )
        elif not self.broker.is_market_open():
            logger.info("cycle %s: market closed, no decision", self.cycle_id)
            return self._finish(STATUS_SKIPPED, "market closed", None, {})
        portfolio, halted = self._load_portfolio()
        self._step(
            CYCLE_SCOPE,
            "portfolio",
            PortfolioSnapshot,
            lambda: snapshot(portfolio, halted),
        )
        outcomes = {symbol: self._analyze(symbol) for symbol in self.config.market.symbols}
        self._apply_risk(outcomes, portfolio, halted)
        errors = [f"{s}: {o.error}" for s, o in outcomes.items() if o.error is not None]
        status = STATUS_ERROR if errors else STATUS_SUCCESS
        return self._finish(status, "; ".join(errors), halted, outcomes)

    def _finish(
        self, status: str, detail: str, halted: str | None, outcomes: dict[str, SymbolOutcome]
    ) -> CycleReport:
        self.store.finish_cycle(self.cycle_id, status, detail)
        return CycleReport(status=status, detail=detail, halted_reason=halted, outcomes=outcomes)

    def _step[T: BaseModel](
        self, symbol: str, name: str, model: type[T], action: Callable[[], T]
    ) -> T:
        """Run an external action once; if the journal holds its result, read it back."""
        cached = self.store.get_step(self.cycle_id, symbol, name)
        if cached is not None:
            return model.model_validate_json(cached)
        result = action()
        self.store.save_step(self.cycle_id, symbol, name, result.model_dump_json())
        return result

    def _fail(self, symbol: str, message: str) -> str:
        logger.warning("cycle %s: %s: %s", self.cycle_id, symbol, message)
        self.store.save_step(self.cycle_id, symbol, "error", json.dumps({"message": message}))
        return message

    def _load_portfolio(self) -> tuple[Portfolio, str | None]:
        risk = self.config.risk
        account_equity = self.broker.get_equity()
        baseline = float(self.store.get_or_set_state(BASELINE_KEY, str(account_equity)))
        equity = risk.allocated_capital + account_equity - baseline
        today = datetime.now(UTC).date().isoformat()
        day_start = float(self.store.get_or_set_state(DAY_START_KEY + today, str(equity)))
        allowed = set(self.config.market.symbols)
        positions = {s: p for s, p in self.broker.get_positions().items() if s in allowed}
        halted = self.store.get_state(HALTED_KEY)
        if halted is None:
            halted = halt_reason(equity, risk)
            if halted is not None:
                self.store.set_state(HALTED_KEY, halted)
                logger.error("cycle %s: HALTED: %s", self.cycle_id, halted)
        return Portfolio(equity=equity, day_start_equity=day_start, positions=positions), halted

    def _get_inputs(self) -> tuple[list[Bar], TimestralForecaster, datetime]:
        if self._inputs is None:
            now = datetime.now(UTC)
            start = now - timedelta(days=self.config.market.history_days)
            bars = self.broker.fetch_hourly_bars(self.config.market.symbols, start, now)
            self._inputs = (bars, load_model(self.config.forecast.model), now)
        return self._inputs

    def _forecast(self, symbol: str) -> PriceForecast:
        bars, forecaster, now = self._get_inputs()
        market = self.config.market
        series = build_series(symbol, bars, self.config.forecast.context_length, now, market)
        if not self.ignore_market_clock:
            check_freshness(series, now, market)
        return forecast_symbol(forecaster, series, self.config.forecast)

    def _analyze(self, symbol: str) -> SymbolOutcome:
        try:
            forecast = self._step(symbol, "forecast", PriceForecast, lambda: self._forecast(symbol))
        except (DataError, ForecastError, BrokerError) as error:
            return SymbolOutcome(error=self._fail(symbol, str(error)))
        try:
            decision = self._step(
                symbol,
                "llm",
                Decision,
                lambda: decide(self.llm_client, forecast, self.config.llm, self.cycle_id),
            )
        except LlmError as error:
            return SymbolOutcome(forecast=forecast, error=self._fail(symbol, str(error)))
        return SymbolOutcome(forecast=forecast, decision=decision)

    def _apply_risk(
        self, outcomes: dict[str, SymbolOutcome], portfolio: Portfolio, halted: str | None
    ) -> None:
        by_confidence = sorted(
            (item for item in outcomes.items() if item[1].decision is not None),
            key=lambda item: item[1].decision.confidence,  # type: ignore[union-attr]
            reverse=True,
        )
        approved_count = 0
        for symbol, outcome in by_confidence:
            verdict = self._verdict(symbol, outcome, portfolio, halted, approved_count)
            outcome.verdict = verdict
            if verdict.approved:
                approved_count += 1
                _apply_to_portfolio(portfolio, verdict)
                if self.execute:
                    self._send_order(symbol, outcome, verdict)

    def _verdict(
        self,
        symbol: str,
        outcome: SymbolOutcome,
        portfolio: Portfolio,
        halted: str | None,
        approved_count: int,
    ) -> Verdict:
        decision, forecast = outcome.decision, outcome.forecast
        assert decision is not None and forecast is not None
        return self._step(
            symbol,
            "verdict",
            Verdict,
            lambda: evaluate(
                decision,
                forecast,
                portfolio,
                self.config.risk,
                self.config.market.symbols,
                halted,
                approved_count,
            ),
        )

    def _send_order(self, symbol: str, outcome: SymbolOutcome, verdict: Verdict) -> None:
        spec = verdict.order
        assert spec is not None
        client_order_id = f"{self.cycle_id}-{symbol}-{spec.side}"
        try:
            outcome.order = self._step(
                symbol,
                "order",
                OrderRecord,
                lambda: self.broker.submit_order(spec, client_order_id),
            )
        except BrokerError as error:
            outcome.error = self._fail(symbol, str(error))


def _apply_to_portfolio(portfolio: Portfolio, verdict: Verdict) -> None:
    """Keep exposure consistent between orders of the same cycle."""
    order = verdict.order
    assert order is not None
    if order.side == "sell":
        portfolio.positions.pop(order.symbol, None)
        return
    held = portfolio.positions.get(order.symbol, Position(qty=0.0, market_value=0.0))
    portfolio.positions[order.symbol] = Position(
        qty=held.qty, market_value=held.market_value + (order.notional or 0.0)
    )
