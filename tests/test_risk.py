from datetime import UTC, datetime

import pytest

from agent.config import RiskConfig
from agent.forecast import PriceForecast
from agent.llm import Decision
from agent.risk import Portfolio, Position, Verdict, evaluate, halt_reason, size_buy

RISK = RiskConfig(
    enabled=True,
    allocated_capital=10_000.0,
    capital_floor=8_000.0,
    max_daily_loss_pct=5.0,
    max_position_pct=20.0,
    max_total_exposure_pct=80.0,
    max_orders_per_cycle=2,
    min_confidence=0.6,
    max_uncertainty=0.06,
)
SYMBOLS = ["SPY", "QQQ"]


def forecast(symbol: str = "SPY", uncertainty: float = 0.0) -> PriceForecast:
    return PriceForecast(
        symbol=symbol,
        model="m",
        last_bar_start=datetime(2026, 11, 10, tzinfo=UTC),
        last_price=100.0,
        median=[101.0],
        lower=[99.0],
        upper=[103.0],
        uncertainty=uncertainty,
    )


def decision(action: str = "buy", confidence: float = 0.9) -> Decision:
    return Decision.model_validate({"action": action, "confidence": confidence, "rationale": "t"})


def portfolio(
    equity: float = 10_000.0,
    day_start: float = 10_000.0,
    positions: dict[str, Position] | None = None,
) -> Portfolio:
    return Portfolio(equity=equity, day_start_equity=day_start, positions=positions or {})


def run(
    dec: Decision | None = None,
    fc: PriceForecast | None = None,
    pf: Portfolio | None = None,
    risk: RiskConfig = RISK,
    halted: str | None = None,
    approved: int = 0,
) -> Verdict:
    return evaluate(
        dec or decision(), fc or forecast(), pf or portfolio(), risk, SYMBOLS, halted, approved
    )


def test_emergency_stop_blocks_everything() -> None:
    verdict = run(risk=RISK.model_copy(update={"enabled": False}))
    assert not verdict.approved and "emergency stop" in verdict.reason


def test_halted_state_blocks_buy_and_sell() -> None:
    held = portfolio(positions={"SPY": Position(qty=1, market_value=100)})
    assert not run(halted="floor", dec=decision("sell"), pf=held).approved
    assert not run(halted="floor").approved


def test_symbol_must_be_allowed() -> None:
    assert not run(fc=forecast("TSLA")).approved


def test_hold_places_no_order() -> None:
    assert not run(dec=decision("hold")).approved


def test_low_confidence_rejected() -> None:
    assert not run(dec=decision(confidence=0.59)).approved
    assert run(dec=decision(confidence=0.6)).approved


def test_max_orders_per_cycle() -> None:
    assert run(approved=1).approved
    assert not run(approved=2).approved


def test_uncertainty_too_high_rejects_buy() -> None:
    assert not run(fc=forecast(uncertainty=0.07)).approved


def test_daily_loss_blocks_buys_but_not_sells() -> None:
    loss = portfolio(
        equity=9_400.0, day_start=10_000.0, positions={"SPY": Position(qty=2, market_value=200)}
    )
    assert not run(pf=loss).approved
    sell = run(dec=decision("sell"), pf=loss)
    assert sell.approved and sell.order is not None and sell.order.qty == 2


def test_sell_without_position_rejected() -> None:
    assert not run(dec=decision("sell")).approved


def test_position_limit_caps_buy() -> None:
    held = portfolio(positions={"SPY": Position(qty=15, market_value=1_500.0)})
    verdict = run(pf=held)
    assert verdict.order is not None and verdict.order.notional == pytest.approx(500.0)


def test_position_already_at_limit_rejected() -> None:
    held = portfolio(positions={"SPY": Position(qty=20, market_value=2_000.0)})
    assert not run(pf=held).approved


def test_total_exposure_caps_buy() -> None:
    full = portfolio(
        positions={
            "QQQ": Position(qty=1, market_value=2_000.0),
            "AAPL": Position(qty=1, market_value=2_000.0),
            "MSFT": Position(qty=1, market_value=2_000.0),
            "GLD": Position(qty=1, market_value=1_900.0),
        }
    )
    verdict = run(pf=full)
    assert verdict.order is not None and verdict.order.notional == pytest.approx(100.0)


def test_wider_interval_means_smaller_position() -> None:
    narrow = size_buy(0.01, "SPY", portfolio(), RISK)
    wide = size_buy(0.05, "SPY", portfolio(), RISK)
    assert narrow > wide > 0
    assert size_buy(0.0, "SPY", portfolio(), RISK) == 2_000.0


def test_capital_floor_halts() -> None:
    assert halt_reason(7_999.0, RISK) is not None
    assert halt_reason(8_000.0, RISK) is None


def test_inconsistent_risk_config_rejected() -> None:
    with pytest.raises(ValueError):
        RiskConfig.model_validate({**RISK.model_dump(), "capital_floor": 10_000.0})
