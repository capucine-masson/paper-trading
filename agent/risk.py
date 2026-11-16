"""Pure client rules and position sizing. Every decision goes through here before the broker."""

from collections.abc import Callable, Iterator
from typing import Literal, NamedTuple

from pydantic import BaseModel

from agent.config import PERCENT, RiskConfig
from agent.forecast import PriceForecast
from agent.llm import Decision

MIN_ORDER_NOTIONAL = 1.0
QTY_DECIMALS = 6


class Position(BaseModel):
    qty: float
    market_value: float


class Portfolio(BaseModel):
    equity: float
    day_start_equity: float
    positions: dict[str, Position]

    @property
    def exposure(self) -> float:
        return sum(position.market_value for position in self.positions.values())

    @property
    def market_values(self) -> dict[str, float]:
        return {symbol: position.market_value for symbol, position in self.positions.items()}


class PortfolioSnapshot(BaseModel):
    """Portfolio at the start of a cycle, journaled to draw the performance curve."""

    equity: float
    day_start_equity: float
    exposure: float
    positions: dict[str, Position]
    halted_reason: str | None


def snapshot(portfolio: Portfolio, halted_reason: str | None) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        equity=portfolio.equity,
        day_start_equity=portfolio.day_start_equity,
        exposure=portfolio.exposure,
        positions=dict(portfolio.positions),
        halted_reason=halted_reason,
    )


class OrderSpec(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    notional: float | None = None
    qty: float | None = None


class Verdict(BaseModel):
    approved: bool
    reason: str
    order: OrderSpec | None = None
    reduced: bool = False


def halt_reason(equity: float, risk: RiskConfig) -> str | None:
    if equity < risk.capital_floor:
        return f"equity ${equity:,.2f} is below the capital floor ${risk.capital_floor:,.2f}"
    return None


def evaluate(
    decision: Decision,
    forecast: PriceForecast,
    portfolio: Portfolio,
    risk: RiskConfig,
    allowed_symbols: list[str],
    halted_reason: str | None,
    orders_approved: int,
) -> Verdict:
    symbol = forecast.symbol
    if not risk.enabled:
        return _rejected("emergency stop: trading is disabled")
    if halted_reason is not None:
        return _rejected(f"halted: {halted_reason}")
    if symbol not in allowed_symbols:
        return _rejected(f"{symbol} is not an allowed symbol")
    if decision.action == "hold":
        return _rejected("hold: no order")
    if decision.confidence < risk.min_confidence:
        return _rejected(f"confidence {decision.confidence:.0%} below {risk.min_confidence:.0%}")
    if orders_approved >= risk.max_orders_per_cycle:
        return _rejected(f"maximum of {risk.max_orders_per_cycle} orders per cycle reached")
    if decision.action == "sell":
        return _sell(decision, symbol, portfolio)
    return _buy(decision, forecast, portfolio, risk)


def _rejected(reason: str) -> Verdict:
    return Verdict(approved=False, reason=reason)


def _sell(decision: Decision, symbol: str, portfolio: Portfolio) -> Verdict:
    position = portfolio.positions.get(symbol)
    if position is None or position.qty <= 0:
        return _rejected(f"no {symbol} position to sell (long only)")
    if decision.size_fraction == 0:
        return _rejected("sell with a size of zero: no order")
    qty = min(round(position.qty * decision.size_fraction, QTY_DECIMALS), position.qty)
    order = OrderSpec(symbol=symbol, side="sell", qty=qty)
    share = (
        "the whole position"
        if qty == position.qty
        else f"{decision.size_fraction:.0%} of the position"
    )
    return Verdict(approved=True, reason=f"sell {share}", order=order)


def _buy(
    decision: Decision,
    forecast: PriceForecast,
    portfolio: Portfolio,
    risk: RiskConfig,
) -> Verdict:
    symbol = forecast.symbol
    if decision.size_fraction == 0:
        return _rejected("buy with a size of zero: no order")
    if risk.forecast_guard and forecast.expected_return <= 0:
        return _rejected(
            f"expected return {forecast.expected_return:+.2%} is not positive: "
            "no buy against the forecast"
        )
    if forecast.uncertainty > risk.max_uncertainty:
        return _rejected(f"uncertainty {forecast.uncertainty:.2%} above {risk.max_uncertainty:.2%}")
    max_daily_loss = risk.max_daily_loss_pct / PERCENT * risk.allocated_capital
    if portfolio.day_start_equity - portfolio.equity > max_daily_loss:
        return _rejected(f"daily loss above ${max_daily_loss:,.2f}: no more buys today")
    position_cap = risk.max_position_pct / PERCENT * risk.allocated_capital
    exposure_cap = risk.max_total_exposure_pct / PERCENT * risk.allocated_capital
    held = portfolio.positions.get(symbol)
    wanted = position_cap * min(
        decision.size_fraction, 1 - forecast.uncertainty / risk.max_uncertainty
    )
    room = min(
        position_cap - (0.0 if held is None else held.market_value),
        exposure_cap - portfolio.exposure,
    )
    notional = round(max(min(wanted, room), 0.0), 2)
    if notional < MIN_ORDER_NOTIONAL:
        return _rejected(f"no room to buy {symbol} within position and exposure limits")
    reduced = notional < round(wanted, 2)
    reason = f"buy ${notional:,.2f}"
    if reduced:
        reason += f", reduced from ${wanted:,.2f} by position and exposure limits"
    order = OrderSpec(symbol=symbol, side="buy", notional=notional)
    return Verdict(approved=True, reason=reason, order=order, reduced=reduced)


class Candidate(NamedTuple):
    symbol: str
    decision: Decision
    forecast: PriceForecast


def evaluate_ranked(
    candidates: list[Candidate],
    portfolio: Portfolio,
    assess: Callable[[Decision, PriceForecast, int], Verdict],
) -> Iterator[tuple[str, Verdict]]:
    """Assess the most confident decisions first; each approved order is applied to the portfolio
    before the next one, so later decisions see the exposure and the order count it leaves."""
    approved = 0
    for symbol, decision, forecast in sorted(
        candidates, key=lambda candidate: candidate.decision.confidence, reverse=True
    ):
        verdict = assess(decision, forecast, approved)
        if verdict.order is not None:
            approved += 1
            apply_to_portfolio(portfolio, verdict.order)
        yield symbol, verdict


def apply_to_portfolio(portfolio: Portfolio, order: OrderSpec) -> None:
    """Keep exposure consistent between orders of the same cycle."""
    if order.side == "sell":
        held_position = portfolio.positions[order.symbol]
        remaining = held_position.qty - (order.qty or 0.0)
        if remaining <= 0:
            portfolio.positions.pop(order.symbol)
        else:
            portfolio.positions[order.symbol] = Position(
                qty=remaining,
                market_value=held_position.market_value * remaining / held_position.qty,
            )
        return
    held = portfolio.positions.get(order.symbol, Position(qty=0.0, market_value=0.0))
    portfolio.positions[order.symbol] = Position(
        qty=held.qty, market_value=held.market_value + (order.notional or 0.0)
    )
