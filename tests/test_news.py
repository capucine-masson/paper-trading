from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from agent.broker import BrokerError
from agent.config import CONFIG_PATH, NewsConfig, load_config
from agent.data import Article
from agent.news import NewsSource, news_count_covariate, news_score_covariate
from agent.store import ArticleScore, Store

DAY_START = datetime(2026, 11, 10, tzinfo=UTC)
HOUR = timedelta(hours=1)


def article(article_id: int, created_at: datetime) -> Article:
    return Article(
        id=article_id, created_at=created_at, headline="h", summary="s", source="x", url=None
    )


class FakeFetch:
    def __init__(self, articles: list[Article] | None = None) -> None:
        self.articles = articles or []
        self.calls: list[tuple[str, datetime, datetime]] = []
        self.fail_next = False

    def __call__(self, symbol: str, start: datetime, end: datetime) -> list[Article]:
        self.calls.append((symbol, start, end))
        if self.fail_next:
            self.fail_next = False
            raise BrokerError("boom")
        return [a for a in self.articles if start <= a.created_at <= end]


def make_source(tmp_path: Path, fetch: FakeFetch) -> NewsSource:
    config: NewsConfig = load_config(CONFIG_PATH).news.model_copy(update={"request_interval_s": 0})
    return NewsSource(Store(tmp_path / "j.db", news_tables=True), fetch, config)


def test_articles_are_point_in_time(tmp_path: Path) -> None:
    fetch = FakeFetch([article(i, DAY_START + HOUR * i) for i in range(1, 6)])
    found = make_source(tmp_path, fetch).articles("SPY", DAY_START + HOUR, DAY_START + HOUR * 4)
    assert [a.id for a in found] == [2, 3, 4]  # (after, until]: nothing later than `until`


def test_past_days_are_fetched_once(tmp_path: Path) -> None:
    fetch = FakeFetch()
    source = make_source(tmp_path, fetch)
    source.articles("SPY", DAY_START, DAY_START + timedelta(days=1, hours=3))
    assert [(c[1], c[2]) for c in fetch.calls] == [
        (DAY_START, DAY_START + timedelta(days=1)),
        (DAY_START + timedelta(days=1), DAY_START + timedelta(days=2)),
    ]
    source.articles("SPY", DAY_START, DAY_START + timedelta(days=1, hours=3))
    assert len(fetch.calls) == 2


def test_cache_survives_a_restart(tmp_path: Path) -> None:
    fetch = FakeFetch([article(1, DAY_START + HOUR)])
    make_source(tmp_path, fetch).articles("SPY", DAY_START, DAY_START + HOUR * 2)
    again = make_source(tmp_path, fetch).articles("SPY", DAY_START, DAY_START + HOUR * 2)
    assert len(fetch.calls) == 1
    assert [a.id for a in again] == [1]


def test_running_day_is_refetched_and_capped_at_now(tmp_path: Path) -> None:
    fetch = FakeFetch()
    source = make_source(tmp_path, fetch)
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    source.sync("SPY", today, now)
    source.sync("SPY", today, now)
    assert len(fetch.calls) == 2
    assert all(call[2] <= datetime.now(UTC) for call in fetch.calls)


def test_future_days_are_not_requested(tmp_path: Path) -> None:
    fetch = FakeFetch()
    now = datetime.now(UTC)
    make_source(tmp_path, fetch).sync("SPY", now, now + timedelta(days=3))
    assert len(fetch.calls) == 1


def test_failed_day_is_not_cached(tmp_path: Path) -> None:
    fetch = FakeFetch()
    source = make_source(tmp_path, fetch)
    fetch.fail_next = True
    with pytest.raises(BrokerError):
        source.sync("SPY", DAY_START, DAY_START + HOUR)
    source.sync("SPY", DAY_START, DAY_START + HOUR)
    assert len(fetch.calls) == 2


def test_symbols_are_cached_separately(tmp_path: Path) -> None:
    fetch = FakeFetch()
    source = make_source(tmp_path, fetch)
    source.sync("SPY", DAY_START, DAY_START + HOUR)
    source.sync("QQQ", DAY_START, DAY_START + HOUR)
    assert [c[0] for c in fetch.calls] == ["SPY", "QQQ"]


# --- covariate ------------------------------------------------------------------------------

SLOTS = [DAY_START + timedelta(hours=14 + i) for i in range(6)]  # bars 14:00 to 19:00


def counts(created_at: list[datetime], window_bars: int) -> list[float]:
    return [float(x) for x in news_count_covariate(SLOTS, sorted(created_at), window_bars)]


def test_no_article_means_zero() -> None:
    assert counts([], 3) == [0.0] * 6


def test_article_is_counted_in_the_bar_that_contains_it_and_the_window_after() -> None:
    created = [DAY_START + timedelta(hours=16, minutes=30)]  # in bar 16:00, which ends at 17:00
    assert counts(created, 2) == [0.0, 0.0, 1.0, 1.0, 0.0, 0.0]


def test_article_is_never_counted_before_it_exists() -> None:
    created = [DAY_START + timedelta(hours=16, minutes=30)]
    assert counts(created, 6)[:2] == [0.0, 0.0]


def test_article_at_the_end_of_a_bar_is_included_but_not_the_next_second() -> None:
    at_end = DAY_START + timedelta(hours=15)
    assert counts([at_end], 1)[0] == 1.0
    assert counts([at_end + timedelta(seconds=1)], 1)[:2] == [0.0, 1.0]


def test_overnight_articles_land_in_the_next_session_bar() -> None:
    slots = [DAY_START + timedelta(hours=19), DAY_START + timedelta(days=1, hours=14)]
    created = [DAY_START + timedelta(hours=23), DAY_START + timedelta(days=1, hours=3)]
    assert news_count_covariate(slots, created, 1).tolist() == [0.0, 2.0]


def test_window_larger_than_the_series() -> None:
    created = [DAY_START + timedelta(hours=14, minutes=10)]
    assert counts(created, 50) == [1.0] * 6


def test_article_before_the_series_is_ignored() -> None:
    assert counts([DAY_START + timedelta(hours=1)], 3) == [0.0] * 6


def score_values(items: list[tuple[datetime, float, float]], window_bars: int) -> list[float]:
    items = sorted(items)
    values = news_score_covariate(
        SLOTS, [t for t, _, _ in items], [ArticleScore(s, r) for _, s, r in items], window_bars
    )
    return [float(x) for x in values]


def test_score_is_nan_without_news() -> None:
    assert all(np.isnan(score_values([], 3)))


def test_score_is_the_relevance_weighted_mean_sentiment() -> None:
    at = DAY_START + timedelta(hours=14, minutes=10)
    values = score_values([(at, 1.0, 0.75), (at, -1.0, 0.25)], 6)
    assert values[0] == pytest.approx(0.5)
    assert values[5] == pytest.approx(0.5)


def test_score_ignores_zero_relevance() -> None:
    at = DAY_START + timedelta(hours=14, minutes=10)
    assert all(np.isnan(score_values([(at, 1.0, 0.0)], 6)))


def test_score_window_forgets_old_news_and_never_sees_the_future() -> None:
    at = DAY_START + timedelta(hours=15, minutes=30)  # bar 15:00, ends 16:00 (slot 1)
    values = score_values([(at, 0.8, 1.0)], 2)
    assert np.isnan(values[0])
    assert values[1] == pytest.approx(0.8) and values[2] == pytest.approx(0.8)
    assert np.isnan(values[3])
