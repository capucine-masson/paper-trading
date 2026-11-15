"""A/B backtest of the news covariates: the same walk-forward points, with and without them."""

import argparse
import logging
import math
from datetime import UTC, datetime, timedelta

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from agent.backtest import (
    EvalPoint,
    ForecastRecord,
    ModelResult,
    bars_range,
    build_points,
    evaluate_model,
    run_forecasts,
)
from agent.broker import Broker
from agent.config import REPORTS_DIR, Config, load_config, load_secrets
from agent.data import Article, Bar
from agent.forecast import load_model
from agent.llm import make_client
from agent.news import NewsSource, news_count_covariate, news_score_covariate
from agent.news_score import PURPOSE, NewsScorer, cost_usd
from agent.store import ArticleScore, Store

logger = logging.getLogger(__name__)

NEWS_CACHE_PATH = REPORTS_DIR / "news_cache.db"
LOW_VOLUME_ARTICLES_PER_WEEK = 25.0
Z_95 = 1.96
DAYS_PER_WEEK = 7
MIN_PAIRS = 30

Covariates = dict[tuple[str, datetime], NDArray[np.float64]]


class PairedComparison(BaseModel):
    """Absolute error at the horizon, with news minus without (negative means news is better)."""

    n: int
    mean_error_change: float
    relative_change: float
    ci_low: float
    ci_high: float
    share_better: float
    verdict: str


class VariantResult(BaseModel):
    """One covariate against the baseline, both evaluated on exactly the same points."""

    name: str
    description: str
    symbols: list[str]
    baseline: ModelResult
    result: ModelResult
    paired: PairedComparison
    paired_per_symbol: dict[str, PairedComparison]


class ScoringStats(BaseModel):
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    scored_articles: int
    unscored_articles: int
    failed_batches: int


class NewsAbReport(BaseModel):
    generated_at: datetime
    symbols: list[str]
    window_bars: int
    horizon_bars: int
    stride_bars: int
    history_start: datetime
    history_end: datetime
    articles_per_week: dict[str, float]
    low_volume_symbols: list[str]
    variants: list[VariantResult]
    scoring: ScoringStats | None


def _errors(records: list[ForecastRecord]) -> dict[tuple[str, datetime], float]:
    return {
        (r.forecast.symbol, r.point.time): abs(r.sample.median - r.sample.actual) for r in records
    }


def paired_comparison(
    without: list[ForecastRecord], with_news: list[ForecastRecord]
) -> PairedComparison:
    """Compare both variants on the points they share; the 95% interval is optimistic because
    consecutive points overlap in time."""
    base, news = _errors(without), _errors(with_news)
    keys = sorted(base.keys() & news.keys())
    diffs = np.array([news[k] - base[k] for k in keys])
    base_mean = float(np.mean([base[k] for k in keys])) if keys else float("nan")
    mean = float(diffs.mean()) if keys else float("nan")
    half_width = Z_95 * float(diffs.std(ddof=1)) / math.sqrt(len(keys)) if len(keys) > 1 else 0.0
    low, high = mean - half_width, mean + half_width
    return PairedComparison(
        n=len(keys),
        mean_error_change=mean,
        relative_change=mean / base_mean if base_mean else float("nan"),
        ci_low=low,
        ci_high=high,
        share_better=float((diffs < 0).mean()) if keys else float("nan"),
        verdict=_verdict(len(keys), low, high),
    )


def _verdict(pairs: int, low: float, high: float) -> str:
    if pairs < MIN_PAIRS:
        return "Too few points to conclude."
    if high < 0:
        return "News lowers the median error (interval excludes zero)."
    if low > 0:
        return "News raises the median error (interval excludes zero)."
    return "No measurable difference (interval includes zero)."


def count_covariates(
    points: list[EvalPoint], articles: dict[str, list[Article]], window_bars: int
) -> Covariates:
    return {
        (p.series.symbol, p.time): news_count_covariate(
            p.series.slot_starts, [a.created_at for a in articles[p.series.symbol]], window_bars
        )
        for p in points
    }


def score_covariates(
    points: list[EvalPoint],
    articles: dict[str, list[Article]],
    scores: dict[str, dict[int, ArticleScore]],
    window_bars: int,
) -> Covariates:
    """Mean sentiment per point; articles the LLM could not score are left out."""
    covariates: Covariates = {}
    for p in points:
        symbol = p.series.symbol
        kept = [a for a in articles[symbol] if a.id in scores[symbol]]
        covariates[(symbol, p.time)] = news_score_covariate(
            p.series.slot_starts,
            [a.created_at for a in kept],
            [scores[symbol][a.id] for a in kept],
            window_bars,
        )
    return covariates


def load_articles(
    source: NewsSource, store: Store, points: list[EvalPoint], symbols: list[str]
) -> dict[str, list[Article]]:
    """Fetch (once, cached) the articles covering every context window, per symbol."""
    found: dict[str, list[Article]] = {}
    for symbol in symbols:
        mine = [p for p in points if p.series.symbol == symbol]
        after = min(p.series.slot_starts[0] for p in mine)
        until = max(p.time for p in mine)
        source.sync(symbol, after, until)
        found[symbol] = store.list_articles(symbol, after, until)
    return found


def articles_per_week(
    articles: dict[str, list[Article]], start: datetime, end: datetime
) -> dict[str, float]:
    weeks = (end - start).total_seconds() / timedelta(days=DAYS_PER_WEEK).total_seconds()
    return {
        s: sum(start < a.created_at <= end for a in found) / weeks for s, found in articles.items()
    }


def build_variant(
    name: str,
    description: str,
    model: str,
    baseline: list[ForecastRecord],
    records: list[ForecastRecord],
) -> VariantResult:
    keys = {(r.forecast.symbol, r.point.time) for r in records}
    same_points = [r for r in baseline if (r.forecast.symbol, r.point.time) in keys]
    symbols = sorted({r.forecast.symbol for r in records})
    return VariantResult(
        name=name,
        description=description,
        symbols=symbols,
        baseline=evaluate_model("Without news", model, same_points),
        result=evaluate_model(name, model, records),
        paired=paired_comparison(same_points, records),
        paired_per_symbol={
            s: paired_comparison(
                [r for r in same_points if r.forecast.symbol == s],
                [r for r in records if r.forecast.symbol == s],
            )
            for s in symbols
        },
    )


def _scoring_stats(
    store: Store, articles: dict[str, list[Article]], symbols: list[str], failed: int
) -> ScoringStats:
    usage = store.llm_usage(PURPOSE)
    total = sum(len(articles[s]) for s in symbols)
    done = sum(len(store.get_scores(s)) for s in symbols)
    return ScoringStats(
        calls=usage.calls,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cost_usd=cost_usd(usage),
        scored_articles=done,
        unscored_articles=total - done,
        failed_batches=failed,
    )


def run_news_ab(
    config: Config, bars: list[Bar], broker: Broker, store: Store, scorer: NewsScorer | None
) -> NewsAbReport:
    points = build_points(bars, config)
    logger.info("%d evaluation points", len(points))
    window = config.news.window_bars
    source = NewsSource(store, broker.fetch_news, config.news)
    articles = load_articles(source, store, points, config.market.symbols)
    model = config.forecast.model
    forecaster = load_model(model)
    baseline = run_forecasts(points, forecaster, config, model)
    counts = run_forecasts(
        points, forecaster, config, model, count_covariates(points, articles, window)
    )
    variants = [
        build_variant(
            "Article count",
            f"Number of articles over the last {window} bars (past-only covariate).",
            model,
            baseline,
            counts,
        )
    ]
    scoring: ScoringStats | None = None
    if scorer is not None:
        scored_symbols = config.news.scored_symbols
        failed = sum(scorer.score_missing(s, articles[s]) for s in scored_symbols)
        scores = {s: store.get_scores(s) for s in scored_symbols}
        scored_points = [p for p in points if p.series.symbol in scored_symbols]
        covariates = score_covariates(scored_points, articles, scores, window)
        variants.append(
            build_variant(
                "LLM sentiment",
                f"Relevance-weighted mean sentiment over the last {window} bars, "
                "NaN with no news (past-only covariate).",
                model,
                baseline,
                run_forecasts(scored_points, forecaster, config, model, covariates),
            )
        )
        scoring = _scoring_stats(store, articles, scored_symbols, failed)
    start, end = bars_range(bars)
    volume = articles_per_week(articles, min(p.time for p in points), max(p.time for p in points))
    return NewsAbReport(
        generated_at=datetime.now(UTC),
        symbols=config.market.symbols,
        window_bars=window,
        horizon_bars=config.forecast.horizon,
        stride_bars=config.backtest.stride_bars,
        history_start=start,
        history_end=end,
        articles_per_week=volume,
        low_volume_symbols=[s for s, v in volume.items() if v < LOW_VOLUME_ARTICLES_PER_WEEK],
        variants=variants,
        scoring=scoring,
    )


def _variant_markdown(report: NewsAbReport, v: VariantResult) -> list[str]:
    p = v.paired
    lines = [
        "",
        f"### {v.name}",
        "",
        f"{v.description} Symbols: {', '.join(v.symbols)}.",
        "",
        "| Variant | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in (v.baseline, v.result):
        o = m.overall
        lines.append(
            f"| {m.label} | {o.n} | {o.mae_ratio:.3f} "
            f"| {o.direction_hit_rate:.1%} (n={o.direction_n}) | {o.coverage:.1%} |"
        )
    lines += [
        "",
        f"Paired change of the absolute error: {p.mean_error_change:+.4f} USD "
        f"({p.relative_change:+.2%}), 95% interval [{p.ci_low:+.4f}, {p.ci_high:+.4f}], "
        f"news better on {p.share_better:.0%} of {p.n} points. **{p.verdict}**",
        "",
        "| Symbol | Articles per week | MAE ratio without | MAE ratio with | Verdict |",
        "| --- | --- | --- | --- | --- |",
    ]
    for symbol in v.symbols:
        flag = " (low volume)" if symbol in report.low_volume_symbols else ""
        lines.append(
            f"| {symbol} | {report.articles_per_week[symbol]:.0f}{flag} "
            f"| {v.baseline.per_symbol[symbol].mae_ratio:.3f} "
            f"| {v.result.per_symbol[symbol].mae_ratio:.3f} "
            f"| {v.paired_per_symbol[symbol].verdict} |"
        )
    return lines


def _markdown(report: NewsAbReport) -> str:
    lines = [
        f"Symbols: {', '.join(report.symbols)}. Horizon: {report.horizon_bars} hourly bars. "
        f"Price history {report.history_start:%Y-%m-%d} to {report.history_end:%Y-%m-%d}. "
        f"Low-volume symbols: {', '.join(report.low_volume_symbols) or 'none'}."
    ]
    for variant in report.variants:
        lines += _variant_markdown(report, variant)
    if report.scoring is not None:
        c = report.scoring
        lines += [
            "",
            "### LLM scoring cost",
            "",
            f"{c.calls} calls, {c.prompt_tokens:,} input and {c.completion_tokens:,} output "
            f"tokens, ${c.cost_usd:.2f}. {c.scored_articles} articles scored, "
            f"{c.unscored_articles} left unscored ({c.failed_batches} failed batches).",
        ]
    lines += [
        "",
        "Limits: points are spaced by the stride and overlap in time, so the intervals are "
        "optimistic; one market regime; a single Timestral run per variant.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B backtest of the news covariates")
    parser.add_argument(
        "--score", action="store_true", help="also run the LLM sentiment variant (paid calls)"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    secrets = load_secrets()
    broker = Broker(secrets, config.market.feed, config.broker)
    end = datetime.now(UTC)
    bars = broker.fetch_hourly_bars(
        config.market.symbols, end - timedelta(days=config.backtest.history_days), end
    )
    NEWS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = Store(NEWS_CACHE_PATH, news_tables=True)
    scorer = NewsScorer(store, make_client(secrets, config.llm), config) if args.score else None
    report = run_news_ab(config, bars, broker, store, scorer)
    store.close()
    (REPORTS_DIR / "news_ab.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown = _markdown(report)
    (REPORTS_DIR / "news_ab.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
