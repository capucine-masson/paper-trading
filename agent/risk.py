"""Pure client rules and position sizing. Every decision goes through here before the broker."""

from typing import Literal

from pydantic import BaseModel

from agent.config import RiskConfig
from agent.forecast import PriceForecast
from agent.llm import Decision

PERCENT = 100.0
MIN_ORDER_NOTIONAL = 1.0


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
        return _rejected(f"confidence {decision.confidence:.2f} below {risk.min_confidence:.2f}")
    if orders_approved >= risk.max_orders_per_cycle:
        return _rejected(f"maximum of {risk.max_orders_per_cycle} orders per cycle reached")
    if decision.action == "sell":
        return _sell(symbol, portfolio)
    return _buy(forecast, portfolio, risk)


def _rejected(reason: str) -> Verdict:
    return Verdict(approved=False, reason=reason)


def _sell(symbol: str, portfolio: Portfolio) -> Verdict:
    position = portfolio.positions.get(symbol)
    if position is None or position.qty <= 0:
        return _rejected(f"no {symbol} position to sell (long only)")
    order = OrderSpec(symbol=symbol, side="sell", qty=position.qty)
    return Verdict(approved=True, reason="sell the whole position", order=order)


def _buy(forecast: PriceForecast, portfolio: Portfolio, risk: RiskConfig) -> Verdict:
    symbol = forecast.symbol
    if forecast.uncertainty > risk.max_uncertainty:
        return _rejected(f"uncertainty {forecast.uncertainty:.2%} above {risk.max_uncertainty:.2%}")
    max_daily_loss = risk.max_daily_loss_pct / PERCENT * risk.allocated_capital
    if portfolio.day_start_equity - portfolio.equity > max_daily_loss:
        return _rejected(f"daily loss above ${max_daily_loss:,.2f}: no more buys today")
    notional = size_buy(forecast.uncertainty, symbol, portfolio, risk)
    if notional < MIN_ORDER_NOTIONAL:
        return _rejected(f"no room to buy {symbol} within position and exposure limits")
    order = OrderSpec(symbol=symbol, side="buy", notional=notional)
    return Verdict(approved=True, reason=f"buy ${notional:,.2f}", order=order)


def size_buy(uncertainty: float, symbol: str, portfolio: Portfolio, risk: RiskConfig) -> float:
    """Wider forecast interval, smaller position; capped by position and exposure room."""
    position_cap = risk.max_position_pct / PERCENT * risk.allocated_capital
    exposure_cap = risk.max_total_exposure_pct / PERCENT * risk.allocated_capital
    held = portfolio.positions.get(symbol)
    held_value = 0.0 if held is None else held.market_value
    target = position_cap * (1 - uncertainty / risk.max_uncertainty)
    room = min(target, position_cap - held_value, exposure_cap - portfolio.exposure)
    return round(max(room, 0.0), 2)
