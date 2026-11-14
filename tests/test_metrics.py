import pytest

from agent.metrics import (
    ForecastSample,
    buy_and_hold_curve,
    forecast_metrics,
    max_drawdown,
)


def sample(last: float, median: float, lower: float, upper: float, actual: float) -> ForecastSample:
    return ForecastSample(last=last, median=median, lower=lower, upper=upper, actual=actual)


def test_forecast_metrics_known_values() -> None:
    samples = [
        sample(100, 102, 98, 106, 103),  # direction hit, inside the interval
        sample(100, 98, 95, 101, 102),  # direction miss, outside the interval
    ]
    m = forecast_metrics(samples)
    assert m.n == 2
    assert m.mae_model == pytest.approx((1 + 4) / 2)
    assert m.mae_naive == pytest.approx((3 + 2) / 2)
    assert m.mae_ratio == pytest.approx(1.0)
    assert m.direction_hit_rate == pytest.approx(0.5)
    assert m.coverage == pytest.approx(0.5)
    assert m.mean_width == pytest.approx((0.08 + 0.06) / 2)


def test_perfect_forecast_beats_naive() -> None:
    m = forecast_metrics([sample(100, 105, 100, 110, 105), sample(100, 95, 90, 100, 95)])
    assert m.mae_model == 0 and m.mae_ratio == 0 and m.direction_hit_rate == 1.0


def test_unchanged_price_is_ignored_for_direction() -> None:
    m = forecast_metrics([sample(100, 101, 99, 103, 100), sample(100, 101, 99, 103, 102)])
    assert m.direction_n == 1 and m.direction_hit_rate == 1.0


def test_no_sample_is_an_error() -> None:
    with pytest.raises(ValueError):
        forecast_metrics([])


def test_max_drawdown() -> None:
    assert max_drawdown([100, 120, 90, 110]) == pytest.approx(0.25)
    assert max_drawdown([100, 101, 102]) == 0.0


def test_buy_and_hold_is_bought_once_and_never_rebalanced() -> None:
    prices = [{"A": 100.0, "B": 50.0}, {"A": 110.0, "B": 50.0}, {"A": 110.0, "B": 60.0}]
    curve = buy_and_hold_curve(prices, ["A", "B"], 1_000.0)
    # 5 units of A and 10 units of B, bought at the first cycle
    assert curve == pytest.approx([1_000.0, 1_050.0, 1_150.0])


def test_buy_and_hold_waits_for_every_symbol_and_never_fills_a_gap() -> None:
    prices = [{"A": 100.0}, {"A": 100.0, "B": 50.0}, {"A": 100.0}, {"A": 120.0, "B": 50.0}]
    curve = buy_and_hold_curve(prices, ["A", "B"], 1_000.0)
    assert curve[0] is None and curve[2] is None
    assert curve[1] == pytest.approx(1_000.0)  # starts at the first cycle with every price
    assert curve[3] == pytest.approx(1_100.0)
