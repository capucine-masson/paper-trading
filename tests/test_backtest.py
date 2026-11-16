from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from mistralai.client import Mistral

from agent import backtest as bt
from agent.backtest import (
    EvalPoint,
    ForecastRecord,
    LlmStrategy,
    build_points,
    cash_rule,
    equal_weight_buy_and_hold,
    evaluate_model,
    forecast_points,
    per_symbol,
    simulate,
    timestral_rule,
)
from agent.config import Config, load_config
from agent.data import Bar, PriceSeries
from agent.forecast import PriceForecast
from agent.llm import Decision, Decisions, LlmError, SymbolDecision
from agent.risk import Portfolio, Position
from agent.store import Store

START = datetime(2026, 1, 5, tzinfo=UTC)


@pytest.fixture
def config() -> Config:
    base = load_config()
    return base.model_copy(
        update={
            "market": base.market.model_copy(update={"symbols": ["SPY"]}),
            "forecast": base.forecast.model_copy(update={"context_length": 64, "horizon": 6}),
            "backtest": base.backtest.model_copy(update={"stride_bars": 5}),
        }
    )


def make_bars(count: int = 120) -> list[Bar]:
    return [
        Bar(symbol="SPY", timestamp=START + timedelta(hours=i), close=100.0 + i)
        for i in range(count)
    ]


def test_context_never_contains_future_bars(config: Config) -> None:
    original = build_points(make_bars(), config)
    changed_bars = make_bars()
    cut = 90
    for i in range(cut, len(changed_bars)):
        changed_bars[i] = changed_bars[i].model_copy(update={"close": 9_999.0})
    changed = build_points(changed_bars, config)
    cut_time = START + timedelta(hours=cut)
    compared = 0
    for a, b in zip(original, changed, strict=True):
        if a.time <= cut_time:
            assert np.array_equal(a.series.values, b.series.values, equal_nan=True)
            compared += 1
    assert compared > 3


def test_targets_come_from_the_future_only(config: Config) -> None:
    point = build_points(make_bars(), config)[0]
    last = point.series.last_price
    assert point.fill_price == pytest.approx(last + 1)
    assert point.actual == pytest.approx(last + config.forecast.horizon)


def make_record(
    index: int, price: float, fill: float, median: float | None = None, uncertainty: float = 0.02
) -> ForecastRecord:
    moment = START + timedelta(hours=index)
    series = PriceSeries(
        symbol="SPY",
        last_bar_start=moment - timedelta(hours=1),
        timestamps=[moment - timedelta(hours=1)] * 10,
        values=np.array([price] * 10),
    )
    forecast = PriceForecast(
        symbol="SPY",
        model="m",
        last_bar_start=series.last_bar_start,
        last_price=price,
        median=[median or price],
        lower=[price * 0.99],
        upper=[price * 1.01],
        uncertainty=uncertainty,
    )
    return ForecastRecord(EvalPoint(moment, series, actual=price, fill_price=fill), forecast, 0.0)


def test_forecast_points_keep_the_band_the_median_and_the_actual_price_in_time_order() -> None:
    records = [make_record(2, 102.0, 102.0), make_record(1, 100.0, 100.0, median=101.0)]
    points = forecast_points(records)
    assert [p.t for p in points] == [START + timedelta(hours=1), START + timedelta(hours=2)]
    first = points[0]
    assert (first.symbol, first.lower, first.median, first.upper, first.actual) == (
        "SPY",
        99.0,
        101.0,
        101.0,
        100.0,
    )


def test_exported_points_give_the_same_hit_rate_as_the_table() -> None:
    records = [
        replace(r, point=replace(r.point, actual=102.0 if i % 4 == 0 else 100.0))
        for i, r in enumerate(make_record(i, 100.0, 100.0) for i in range(10))
    ]
    points = forecast_points(records)
    outside = sum(p.actual < p.lower or p.actual > p.upper for p in points)
    assert outside == 3
    assert evaluate_model("m", "m", records).overall.coverage == 1 - outside / len(points)


def test_cash_never_trades(config: Config) -> None:
    records = [make_record(i, 100.0, 100.0) for i in range(5)]
    result = simulate("cash", per_symbol(cash_rule), records, config)
    assert result.trades == 0 and result.return_pct == 0 and result.average_exposure_pct == 0


def test_buy_and_hold_respects_limits_and_earns_in_a_rising_market(config: Config) -> None:
    records = [make_record(i, 100.0 + i, 100.0 + i + 1) for i in range(10)]
    result = simulate("bh", equal_weight_buy_and_hold(config), records, config, False)
    assert result.return_pct > 0 and result.trades == 1
    assert result.average_exposure_pct <= config.risk.max_position_pct + 1.0


def test_fill_is_at_next_bar_close_not_at_decision_price(config: Config) -> None:
    flat = [make_record(0, 100.0, 100.0), make_record(1, 100.0, 100.0)]
    costly = [make_record(0, 100.0, 110.0), make_record(1, 100.0, 110.0)]
    assert (
        simulate("a", equal_weight_buy_and_hold(config), flat, config, False).final_equity
        > simulate("b", equal_weight_buy_and_hold(config), costly, config, False).final_equity
    )


def test_halted_state_stops_trading_after_a_crash(config: Config) -> None:
    risk = config.risk.model_copy(update={"capital_floor": 9_900.0, "max_daily_loss_pct": 100.0})
    cfg = config.model_copy(update={"risk": risk})
    rising = per_symbol(timestral_rule(0.05))  # buys at every decision time

    def records(*prices: float) -> list[ForecastRecord]:
        return [make_record(i, p, p, median=p * 1.01) for i, p in enumerate(prices)]

    calm = records(100.0, 100.0)
    before = simulate("rule", rising, calm, cfg).trades
    after = simulate("rule", rising, calm + records(*([100.0] * 2 + [50.0] * 3))[2:], cfg).trades
    assert after == before


def test_equal_weight_buy_and_hold_buys_each_symbol_once() -> None:
    base = load_config()
    eight = base.model_copy(
        update={"market": base.market.model_copy(update={"symbols": list("ABCDEFGH")})}
    )
    strategy = equal_weight_buy_and_hold(eight)
    record = make_record(0, 100.0, 100.0)
    empty = Portfolio(equity=10_000.0, day_start_equity=10_000.0, positions={})
    held = Portfolio(
        equity=10_000.0,
        day_start_equity=10_000.0,
        positions={"SPY": Position(qty=5.0, market_value=500.0)},
    )
    first = strategy([record], empty)["SPY"]
    assert first.action == "buy" and first.size_fraction == pytest.approx(0.45)
    assert strategy([record], held)["SPY"].action == "hold"


def test_timestral_rule_acts_only_on_a_clear_signal() -> None:
    rule = timestral_rule(0.05)
    assert rule(make_record(0, 100.0, 100.0, median=100.01)).action == "hold"
    assert rule(make_record(0, 100.0, 100.0, median=101.0)).action == "buy"
    assert rule(make_record(0, 100.0, 100.0, median=99.0)).action == "sell"


def test_llm_decisions_are_cached_by_time_and_portfolio(
    config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_decide(*args: object) -> Decisions:
        calls.append("llm")
        decision = Decision(action="buy", confidence=0.9, size_fraction=1.0, rationale="test")
        return Decisions(decisions=[SymbolDecision(symbol="SPY", decision=decision)])

    monkeypatch.setattr(bt, "decide", fake_decide)
    strategy = LlmStrategy(Mistral(api_key="test"), config, Store(tmp_path / "cache.db"))
    group = [make_record(0, 100.0, 100.0)]
    empty = Portfolio(equity=10_000.0, day_start_equity=10_000.0, positions={})
    assert strategy(group, empty)["SPY"].action == "buy"
    assert strategy(group, empty)["SPY"].action == "buy"
    assert calls == ["llm"]
    held = Portfolio(
        equity=10_000.0,
        day_start_equity=10_000.0,
        positions={"SPY": Position(qty=5.0, market_value=500.0)},
    )
    strategy(group, held)
    assert calls == ["llm", "llm"]


def test_llm_failure_means_no_order_at_that_time(
    config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_decide(*args: object) -> Decisions:
        raise LlmError("down")

    monkeypatch.setattr(bt, "decide", failing_decide)
    strategy = LlmStrategy(Mistral(api_key="test"), config, Store(tmp_path / "cache.db"))
    empty = Portfolio(equity=10_000.0, day_start_equity=10_000.0, positions={})
    assert strategy([make_record(0, 100.0, 100.0)], empty) == {} and strategy.failures == 1


def test_cost_lowers_final_equity_and_zero_cost_changes_nothing(config: Config) -> None:
    records = [make_record(i, 100.0, 100.0) for i in range(5)]
    no_cost = config.backtest.model_copy(update={"cost_bps": 0})
    free = config.model_copy(update={"backtest": no_cost})
    bh = equal_weight_buy_and_hold
    gross = simulate("bh", bh(free), records, free, False).final_equity
    net = simulate("bh", bh(config), records, config, False).final_equity
    assert gross == free.risk.allocated_capital
    assert net < gross
