from datetime import UTC, datetime, timedelta

import numpy as np

from agent.backtest import EvalPoint, ForecastRecord
from agent.data import Article, PriceSeries
from agent.forecast import PriceForecast
from agent.news_backtest import (
    articles_per_week,
    count_covariates,
    paired_comparison,
    score_covariates,
)
from agent.store import ArticleScore

START = datetime(2026, 11, 10, 14, tzinfo=UTC)


def record(index: int, median: float, symbol: str = "SPY") -> ForecastRecord:
    moment = START + timedelta(hours=index)
    series = PriceSeries(
        symbol=symbol,
        last_bar_start=moment - timedelta(hours=1),
        slot_starts=[moment - timedelta(hours=3 - i) for i in range(3)],
        values=np.array([100.0, 100.0, 100.0]),
    )
    forecast = PriceForecast(
        symbol=symbol,
        model="m",
        last_bar_start=series.last_bar_start,
        last_price=100.0,
        median=[median],
        lower=[95.0],
        upper=[105.0],
        uncertainty=0.1,
    )
    return ForecastRecord(EvalPoint(moment, series, actual=101.0, fill_price=100.0), forecast, 0.0)


def test_better_news_is_reported_with_its_interval() -> None:
    without = [record(i, 100.0 + (i % 3) * 0.1) for i in range(60)]
    with_news = [record(i, 100.9 + (i % 3) * 0.01) for i in range(60)]
    result = paired_comparison(without, with_news)
    assert result.n == 60
    assert result.mean_error_change < 0 and result.ci_high < 0
    assert result.share_better == 1.0
    assert "lowers" in result.verdict


def test_identical_variants_show_no_difference() -> None:
    same = [record(i, 100.0 + (i % 5) * 0.2) for i in range(60)]
    result = paired_comparison(same, same)
    assert result.mean_error_change == 0.0
    assert "No measurable difference" in result.verdict


def test_worse_news_is_reported() -> None:
    without = [record(i, 100.9 + (i % 3) * 0.01) for i in range(60)]
    with_news = [record(i, 100.0 + (i % 3) * 0.1) for i in range(60)]
    assert "raises" in paired_comparison(without, with_news).verdict


def test_few_points_do_not_conclude() -> None:
    few = [record(i, 100.0) for i in range(5)]
    assert paired_comparison(few, few).verdict == "Too few points to conclude."


def test_only_shared_points_are_compared() -> None:
    result = paired_comparison(
        [record(i, 100.0) for i in range(10)], [record(i, 100.0) for i in range(5, 15)]
    )
    assert result.n == 5


def article(article_id: int, created_at: datetime) -> Article:
    return Article(
        id=article_id, created_at=created_at, headline="h", summary="s", source="x", url=None
    )


def test_covariates_use_only_each_symbol_articles() -> None:
    points = [record(10, 100.0).point, record(10, 100.0, "QQQ").point]
    articles = {"SPY": [article(1, START + timedelta(hours=9, minutes=30))], "QQQ": []}
    covariates = count_covariates(points, articles, window_bars=3)
    assert covariates[("SPY", points[0].time)].tolist() == [0.0, 0.0, 1.0]
    assert covariates[("QQQ", points[1].time)].tolist() == [0.0, 0.0, 0.0]


def test_score_covariate_ignores_unscored_articles_and_is_nan_without_news() -> None:
    points = [record(10, 100.0).point]
    articles = {
        "SPY": [
            article(1, START + timedelta(hours=9, minutes=30)),
            article(2, START + timedelta(hours=9, minutes=40)),
        ]
    }
    scores = {"SPY": {1: ArticleScore(sentiment=0.5, relevance=1.0)}}
    values = score_covariates(points, articles, scores, window_bars=1)[("SPY", points[0].time)]
    assert np.isnan(values[:2]).all()
    assert values[2] == 0.5


def test_articles_per_week() -> None:
    articles = {
        "SPY": [article(d, START + timedelta(days=d)) for d in range(7)],
        "GLD": [],
    }
    volume = articles_per_week(articles, START - timedelta(hours=1), START + timedelta(days=7))
    assert volume["GLD"] == 0.0
    assert 6.9 < volume["SPY"] < 7.1
