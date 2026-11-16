"""One cycle: data, forecast, LLM, risk, order. Every external action is a resumable step."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from mistralai.client import Mistral
from pydantic import BaseModel
from timestral import TimestralForecaster

from agent.broker import Broker, BrokerError, OrderRecord
from agent.config import Config
from agent.data import Bar, DataError, build_series, check_freshness
from agent.forecast import ForecastError, PriceForecast, forecast_symbol, load_model
from agent.llm import Decision, Decisions, LlmError, build_portfolio_data, decide
from agent.macro import MacroData, MacroError, fetch_macro
from agent.risk import (
    Candidate,
    OrderSpec,
    Portfolio,
    PortfolioSnapshot,
    Verdict,
    evaluate,
    evaluate_ranked,
    halt_reason,
    snapshot,
)
from agent.store import (
    ACCOUNT_EQUITY_KEY,
    CYCLE_SCOPE,
    HALTED_KEY,
    STEP_DECISIONS,
    STEP_FORECAST,
    STEP_ORDER,
    STEP_PORTFOLIO,
    STEP_VERDICT,
    Store,
)

logger = logging.getLogger(__name__)

CycleStatus = Literal["success", "error", "skipped"]

STATUS_SUCCESS: CycleStatus = "success"
STATUS_ERROR: CycleStatus = "error"
STATUS_SKIPPED: CycleStatus = "skipped"
BASELINE_KEY = "baseline_equity"
DAY_START_KEY = "day_start_equity:"
FINAL_ORDER_STATUSES = {"filled", "canceled", "expired", "rejected"}
ERROR_STEP = "error"
RECOVERABLE_ERRORS = (DataError, ForecastError, BrokerError, MacroError)


class SymbolOutcome(BaseModel):
    forecast: PriceForecast | None = None
    decision: Decision | None = None
    verdict: Verdict | None = None
    order: OrderRecord | None = None
    error: str | None = None


class CycleReport(BaseModel):
    status: CycleStatus
    detail: str
    halted_reason: str | None = None
    outcomes: dict[str, SymbolOutcome] = {}


@dataclass(frozen=True)
class CycleInputs:
    bars: list[Bar]
    forecaster: TimestralForecaster
    macro: MacroData
    now: datetime


@dataclass
class Cycle:
    config: Config
    broker: Broker
    llm_client: Mistral
    store: Store
    cycle_id: str
    execute: bool
    ignore_market_clock: bool
    fred_api_key: str
    _inputs: CycleInputs | None = field(default=None, init=False)

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
            STEP_PORTFOLIO,
            PortfolioSnapshot,
            lambda: snapshot(portfolio, halted),
        )
        outcomes = self._analyze(portfolio)
        self._apply_risk(outcomes, portfolio, halted)
        errors = [f"{s}: {o.error}" for s, o in outcomes.items() if o.error is not None]
        status = STATUS_ERROR if errors else STATUS_SUCCESS
        return self._finish(status, "; ".join(errors), halted, outcomes)

    def _finish(
        self,
        status: CycleStatus,
        detail: str,
        halted: str | None,
        outcomes: dict[str, SymbolOutcome],
    ) -> CycleReport:
        if self.execute:
            self._refresh_fills()
        self.store.finish_cycle(self.cycle_id, status, detail)
        return CycleReport(status=status, detail=detail, halted_reason=halted, outcomes=outcomes)

    def _refresh_fills(self) -> None:
        """Record the fill of orders that were not final when they were journaled."""
        for row in self.store.list_steps(STEP_ORDER):
            record = OrderRecord.model_validate_json(row.result)
            if record.status in FINAL_ORDER_STATUSES:
                continue
            try:
                latest = self.broker.refresh_order(record)
            except BrokerError as error:
                logger.warning("cycle %s: %s: %s", self.cycle_id, row.symbol, error)
                continue
            self.store.update_step(row.cycle_id, row.symbol, STEP_ORDER, latest.model_dump_json())

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

    def _record_error(self, symbol: str, message: str) -> str:
        """Log and journal an error (the first one of a resumed cycle is kept); return it."""
        logger.warning("cycle %s: %s: %s", self.cycle_id, symbol, message)
        if self._journaled_error(symbol) is None:
            self.store.save_step(self.cycle_id, symbol, ERROR_STEP, message)
        return message

    def _journaled_error(self, symbol: str) -> str | None:
        return self.store.get_step(self.cycle_id, symbol, ERROR_STEP)

    def _load_portfolio(self) -> tuple[Portfolio, str | None]:
        risk = self.config.risk
        account_equity = self.broker.get_equity()
        self.store.set_state(ACCOUNT_EQUITY_KEY, str(account_equity))
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

    def _get_inputs(self) -> CycleInputs:
        if self._inputs is None:
            now = datetime.now(UTC)
            start = now - timedelta(days=self.config.market.history_days)
            bars = self.broker.fetch_hourly_bars(self.config.market.symbols, start, now)
            macro = fetch_macro(
                self.config.macro,
                self.fred_api_key,
                now - timedelta(days=self.config.macro.history_days),
                now,
            )
            self._inputs = CycleInputs(bars, load_model(self.config.forecast), macro, now)
        return self._inputs

    def _forecast(self, symbol: str) -> PriceForecast:
        inputs = self._get_inputs()
        market = self.config.market
        series = build_series(
            symbol, inputs.bars, self.config.forecast.context_length, inputs.now, market
        )
        if not self.ignore_market_clock:
            check_freshness(series, inputs.now, market)
        return forecast_symbol(inputs.forecaster, series, self.config.forecast, inputs.macro)

    def _forecast_step(self, symbol: str) -> PriceForecast:
        """The Timestral tool: run once per symbol and cycle, then read back from the journal."""
        return self._step(symbol, STEP_FORECAST, PriceForecast, lambda: self._forecast(symbol))

    def _forecast_tool(self, symbol: str) -> PriceForecast | None:
        try:
            return self._forecast_step(symbol)
        except RECOVERABLE_ERRORS as error:
            self._record_error(symbol, str(error))
            return None

    def _decide(self, portfolio: Portfolio) -> Decisions:
        """One LLM conversation for all symbols, read back from the journal when already done."""
        if self.store.get_step(self.cycle_id, CYCLE_SCOPE, STEP_DECISIONS) is None:
            self._get_inputs()
        data = build_portfolio_data(
            portfolio.equity,
            self.config.risk.allocated_capital,
            portfolio.day_start_equity,
            portfolio.market_values,
        )
        return self._step(
            CYCLE_SCOPE,
            STEP_DECISIONS,
            Decisions,
            lambda: decide(
                self.llm_client,
                self.config.market.symbols,
                data,
                self._forecast_tool,
                self.config.llm,
                self.cycle_id,
            ),
        )

    def _analyze(self, portfolio: Portfolio) -> dict[str, SymbolOutcome]:
        """A symbol the LLM could not decide gets the error that explains why."""
        symbols = self.config.market.symbols
        try:
            decisions = self._decide(portfolio)
        except (*RECOVERABLE_ERRORS, LlmError) as error:
            message = self._record_error(CYCLE_SCOPE, str(error))
            return {s: SymbolOutcome(error=self._journaled_error(s) or message) for s in symbols}
        decided = decisions.by_symbol()
        return {
            symbol: SymbolOutcome(forecast=self._forecast_step(symbol), decision=decided[symbol])
            if symbol in decided
            else SymbolOutcome(
                error=self._journaled_error(symbol) or "no forecast requested by the LLM"
            )
            for symbol in symbols
        }

    def _apply_risk(
        self, outcomes: dict[str, SymbolOutcome], portfolio: Portfolio, halted: str | None
    ) -> None:
        candidates = [
            Candidate(symbol, outcome.decision, outcome.forecast)
            for symbol, outcome in outcomes.items()
            if outcome.decision is not None and outcome.forecast is not None
        ]
        for symbol, verdict in evaluate_ranked(
            candidates,
            portfolio,
            lambda decision, forecast, approved: self._verdict(
                forecast.symbol, decision, forecast, portfolio, halted, approved
            ),
        ):
            outcomes[symbol].verdict = verdict
            if verdict.order is not None and self.execute:
                self._send_order(symbol, outcomes[symbol], verdict.order)

    def _verdict(
        self,
        symbol: str,
        decision: Decision,
        forecast: PriceForecast,
        portfolio: Portfolio,
        halted: str | None,
        approved_count: int,
    ) -> Verdict:
        return self._step(
            symbol,
            STEP_VERDICT,
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

    def _send_order(self, symbol: str, outcome: SymbolOutcome, spec: OrderSpec) -> None:
        client_order_id = f"{self.cycle_id}-{symbol}-{spec.side}"
        try:
            outcome.order = self._step(
                symbol,
                STEP_ORDER,
                OrderRecord,
                lambda: self.broker.submit_order(spec, client_order_id),
            )
        except BrokerError as error:
            outcome.error = self._record_error(symbol, str(error))
