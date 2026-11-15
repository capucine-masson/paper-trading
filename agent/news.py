"""Alpaca news: cached per symbol and day, turned into a past-only covariate without look-ahead.

The covariate is the number of articles tagged with the symbol, counted over the last N hourly
bars of the series. An hour without article counts 0 (the API covers the whole history, so no
article really means none). Articles published between two consecutive bars of the series
(overnight, weekend) are counted in the next bar.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
from numpy.typing import NDArray

from agent.config import NewsConfig
from agent.data import BAR_PERIOD, Article
from agent.store import ArticleScore, Store

logger = logging.getLogger(__name__)

DAY = timedelta(days=1)
MIN_RELEVANCE_MASS = 1e-6

FetchNews = Callable[[str, datetime, datetime], list[Article]]


def _floor_day(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


class NewsSource:
    def __init__(self, store: Store, fetch: FetchNews, config: NewsConfig) -> None:
        self._store = store
        self._fetch = fetch
        self._config = config

    def articles(self, symbol: str, after: datetime, until: datetime) -> list[Article]:
        """Articles created in (after, until], oldest first."""
        self.sync(symbol, after, until)
        return self._store.list_articles(symbol, after, until)

    def sync(self, symbol: str, after: datetime, until: datetime) -> None:
        """Fetch the daily windows the cache lacks: past days once, the running day every time."""
        now = datetime.now(UTC)
        first = _floor_day(after)
        days = [first + DAY * i for i in range((_floor_day(until) - first) // DAY + 1)]
        done = self._store.fetched_days(symbol, first, _floor_day(until) + DAY)
        for day in (d for d in days if d < now):
            complete = day + DAY <= now
            if complete and day in done:
                continue
            articles = self._fetch(symbol, day, min(day + DAY, now))
            self._store.save_articles(symbol, articles)
            if complete:
                self._store.mark_day_fetched(symbol, day)
            logger.info("news %s %s: %d articles", symbol, day.date(), len(articles))
            time.sleep(self._config.request_interval_s)


def _window_sum(
    slot_starts: list[datetime],
    created_at: list[datetime],
    weights: NDArray[np.float64],
    window_bars: int,
) -> NDArray[np.float64]:
    """Sum of article weights over the last `window_bars` slots of a price series.

    Slot k covers articles created in (end of slot k-1, end of slot k], so an article is never
    counted before it exists. `created_at` must be sorted; `weights` has one value per article.
    """
    times = np.array([t.timestamp() for t in created_at], dtype=np.float64)
    ends = np.array([(s + BAR_PERIOD).timestamp() for s in slot_starts], dtype=np.float64)
    cumulative = np.concatenate([[0.0], np.cumsum(weights)])
    at_end = cumulative[np.searchsorted(times, ends, side="right")]
    before_first = cumulative[
        np.searchsorted(times, ends[:1] - BAR_PERIOD.total_seconds(), "right")
    ]
    total = np.cumsum(np.diff(at_end, prepend=before_first))
    lagged = np.concatenate([np.zeros(window_bars), total[:-window_bars]])
    return np.asarray(total - lagged[: len(total)], dtype=np.float64)


def news_count_covariate(
    slot_starts: list[datetime], created_at: list[datetime], window_bars: int
) -> NDArray[np.float64]:
    """Article count over the last `window_bars` slots; no article means 0."""
    ones = np.ones(len(created_at), dtype=np.float64)
    return _window_sum(slot_starts, created_at, ones, window_bars)


def news_score_covariate(
    slot_starts: list[datetime],
    created_at: list[datetime],
    scores: list[ArticleScore],
    window_bars: int,
) -> NDArray[np.float64]:
    """Relevance-weighted mean sentiment over the last `window_bars` slots; NaN with no news."""
    relevance = np.array([s.relevance for s in scores], dtype=np.float64)
    weighted = np.array([s.sentiment for s in scores], dtype=np.float64) * relevance
    mass = _window_sum(slot_starts, created_at, relevance, window_bars)
    total = _window_sum(slot_starts, created_at, weighted, window_bars)
    empty = mass < MIN_RELEVANCE_MASS
    return np.where(empty, np.nan, total / np.where(empty, 1.0, mass))
