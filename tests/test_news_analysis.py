import numpy as np

from agent.news_analysis import (
    Interval,
    day_bootstrap,
    news_t_stat,
    ols,
    realized_volatility,
    surprise_covariate,
)


def test_surprise_is_the_count_minus_its_previous_average() -> None:
    counts = np.array([2.0, 4.0, 6.0])
    assert surprise_covariate(counts).tolist() == [2.0, 2.0, 3.0]


def test_realized_volatility_ignores_gaps_and_flat_series() -> None:
    assert realized_volatility(np.array([100.0, 100.0, 100.0])) == 0.0
    assert realized_volatility(np.array([100.0, np.nan, 101.0, 100.0, 102.0])) > 0.0


def test_ols_recovers_a_known_slope_and_its_t_statistic() -> None:
    x = np.linspace(-1, 1, 200)
    y = 0.5 + 2.0 * x + np.random.default_rng(1).normal(0, 0.1, 200)
    assert abs(ols(x[:, None], y)[-1] - 2.0) < 0.05
    assert news_t_stat(x[:, None], y) > 50


def test_day_bootstrap_of_a_constant_has_a_zero_width_interval() -> None:
    days = np.repeat(np.arange(10), 5)
    interval = day_bootstrap(days, lambda idx: 3.0, np.random.default_rng(0))
    assert (interval.estimate, interval.low, interval.high) == (3.0, 3.0, 3.0)


def test_interval_sign_rule() -> None:
    assert Interval(0.2, 0.1, 0.3).excludes_zero(+1)
    assert not Interval(0.2, -0.1, 0.3).excludes_zero(+1)
    assert Interval(-0.2, -0.3, -0.1).excludes_zero(-1)
