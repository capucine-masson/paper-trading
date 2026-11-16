from datetime import UTC, datetime

import pytest

from agent.config import RiskConfig
from agent.forecast import PriceForecast
from agent.llm import Decision
from agent.risk import (
    Candidate,
    Portfolio,
    Position,
    Verdict,
    apply_to_portfolio,
    evaluate,
    evaluate_ranked,
    halt_reason,
)

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
    forecast_guard=True,
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


def decision(action: str = "buy", confidence: float = 0.9, size_fraction: float = 1.0) -> Decision:
    return Decision.model_validate(
        {
            "action": action,
            "confidence": confidence,
            "size_fraction": size_fraction,
            "rationale": "t",
        }
    )


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
    def notional(uncertainty: float) -> float:
        order = run(fc=forecast(uncertainty=uncertainty)).order
        assert order is not None and order.notional is not None
        return order.notional

    assert notional(0.01) > notional(0.05) > 0
    assert notional(0.0) == 2_000.0


def test_llm_size_scales_the_position() -> None:
    verdict = run(dec=decision(size_fraction=0.25))
    assert verdict.order is not None and verdict.order.notional == pytest.approx(500.0)


def test_uncertainty_caps_the_llm_size() -> None:
    verdict = run(dec=decision(size_fraction=1.0), fc=forecast(uncertainty=0.05))
    assert verdict.order is not None and verdict.order.notional == pytest.approx(
        2_000.0 / 6, abs=0.01
    )


def test_buy_with_zero_size_rejected() -> None:
    assert not run(dec=decision(size_fraction=0.0)).approved


def test_capital_floor_halts() -> None:
    assert halt_reason(7_999.0, RISK) is not None
    assert halt_reason(8_000.0, RISK) is None


def test_inconsistent_risk_config_rejected() -> None:
    with pytest.raises(ValueError):
        RiskConfig.model_validate({**RISK.model_dump(), "capital_floor": 10_000.0})


def test_buy_cut_by_room_is_flagged_reduced() -> None:
    held = portfolio(positions={"SPY": Position(qty=15, market_value=1_500.0)})
    assert run(pf=held).reduced
    assert not run().reduced


def test_partial_sell_uses_the_llm_share_of_the_position() -> None:
    held = portfolio(positions={"SPY": Position(qty=10, market_value=1_000.0)})
    verdict = run(dec=decision("sell", size_fraction=0.25), pf=held)
    assert verdict.order is not None and verdict.order.qty == pytest.approx(2.5)
    assert "25%" in verdict.reason


def test_sell_with_zero_size_rejected() -> None:
    held = portfolio(positions={"SPY": Position(qty=10, market_value=1_000.0)})
    assert not run(dec=decision("sell", size_fraction=0.0), pf=held).approved


def test_partial_sell_keeps_the_rest_of_the_position() -> None:
    held = portfolio(positions={"SPY": Position(qty=10, market_value=1_000.0)})
    verdict = run(dec=decision("sell", size_fraction=0.25), pf=held)
    assert verdict.order is not None
    apply_to_portfolio(held, verdict.order)
    assert held.positions["SPY"].qty == pytest.approx(7.5)
    assert held.positions["SPY"].market_value == pytest.approx(750.0)


def test_replayed_sell_of_an_already_sold_position_is_ignored() -> None:
    held = portfolio(positions={"SPY": Position(qty=10, market_value=1_000.0)})
    verdict = run(dec=decision("sell"), pf=held)
    assert verdict.order is not None
    apply_to_portfolio(held, verdict.order)
    apply_to_portfolio(held, verdict.order)
    assert "SPY" not in held.positions


def test_buy_against_the_forecast_is_blocked() -> None:
    below = forecast().model_copy(update={"median": [99.0]})
    flat = forecast().model_copy(update={"median": [100.0]})
    for against in (below, flat):
        verdict = run(fc=against)
        assert not verdict.approved and "against the forecast" in verdict.reason


def test_forecast_guard_can_be_skipped_for_baselines() -> None:
    below = forecast().model_copy(update={"median": [99.0]})
    unguarded = RISK.model_copy(update={"forecast_guard": False})
    assert run(fc=below, risk=unguarded).approved


def test_sell_is_allowed_even_when_the_forecast_is_positive() -> None:
    held = portfolio(positions={"SPY": Position(qty=2, market_value=200)})
    assert run(dec=decision("sell"), pf=held).approved


def test_most_confident_decision_is_assessed_first_and_sees_the_orders_before_it() -> None:
    pf = portfolio()
    candidates = [
        Candidate("SPY", decision(confidence=0.7), forecast("SPY")),
        Candidate("QQQ", decision(confidence=0.9), forecast("QQQ")),
    ]
    seen: list[tuple[str, int]] = []

    def assess(dec: Decision, fc: PriceForecast, approved: int) -> Verdict:
        seen.append((fc.symbol, approved))
        return run(dec, fc, pf, approved=approved)

    verdicts = list(evaluate_ranked(candidates, pf, assess))
    assert seen == [("QQQ", 0), ("SPY", 1)]
    assert [symbol for symbol, _ in verdicts] == ["QQQ", "SPY"]
    assert set(pf.positions) == {"QQQ", "SPY"}
