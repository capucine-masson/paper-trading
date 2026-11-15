"""LLM scoring of news articles for the backtest: batched per symbol and day, cached, capped."""

import logging
from collections import defaultdict
from datetime import date

from mistralai.client import Mistral

from agent.config import Config
from agent.data import Article, Usage
from agent.llm import score_articles
from agent.store import ArticleScore, Store

logger = logging.getLogger(__name__)

PURPOSE = "news_backtest"
MAX_CALLS_PER_BATCH = 2  # one call plus the single retry on invalid output
INPUT_USD_PER_MILLION = 0.15  # Mistral Small 4 (mistral-small-2603), standard tier
OUTPUT_USD_PER_MILLION = 0.6
TOKENS_PER_MILLION = 1_000_000


class ScoringBudgetError(Exception):
    """The one-time cap on scoring calls is reached; scores already obtained stay cached."""


def cost_usd(usage: Usage) -> float:
    return (
        usage.prompt_tokens * INPUT_USD_PER_MILLION
        + usage.completion_tokens * OUTPUT_USD_PER_MILLION
    ) / TOKENS_PER_MILLION


class NewsScorer:
    def __init__(self, store: Store, client: Mistral, config: Config) -> None:
        self._store = store
        self._client = client
        self._config = config

    def pending_batches(self, symbol: str, articles: list[Article]) -> list[list[Article]]:
        """Unscored articles grouped per UTC day, then cut into chunks of the batch size."""
        scored = self._store.get_scores(symbol)
        by_day: dict[date, list[Article]] = defaultdict(list)
        for article in articles:
            if article.id not in scored:
                by_day[article.created_at.date()].append(article)
        size = self._config.news.score_batch_size
        return [
            day_articles[i : i + size]
            for _, day_articles in sorted(by_day.items())
            for i in range(0, len(day_articles), size)
        ]

    def score_missing(self, symbol: str, articles: list[Article]) -> int:
        """Score what the cache lacks; returns the number of batches the LLM got wrong twice."""
        failed = 0
        for batch in self.pending_batches(symbol, articles):
            used = self._store.llm_usage(PURPOSE).calls
            if used + MAX_CALLS_PER_BATCH > self._config.news.max_scoring_calls:
                raise ScoringBudgetError(
                    f"{used} scoring calls made, cap is {self._config.news.max_scoring_calls}"
                )
            scored = score_articles(self._client, symbol, batch, self._config.llm)
            self._store.log_llm_calls(PURPOSE, symbol, scored.usage)
            logger.info(
                "news scoring %s %s: %d items, calls=%d tokens in=%d out=%d",
                symbol,
                batch[0].created_at.date(),
                len(batch),
                scored.usage.calls,
                scored.usage.prompt_tokens,
                scored.usage.completion_tokens,
            )
            if not scored.scores:
                failed += 1
                continue
            self._store.save_scores(
                symbol,
                {batch[s.index].id: ArticleScore(s.sentiment, s.relevance) for s in scored.scores},
            )
        return failed
