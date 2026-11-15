"""EXPERIMENTAL: exploratory analysis of the news signal (see reports/news_analysis_plan.md).

Analysis only: reads the cached articles and LLM scores, makes no LLM call and is not used by
the agent.
Choices are made on the tuning period and confirmed once on the confirmation period.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from numpy.typing import NDArray
from timestral import TimestralForecaster

from agent.backtest import EvalPoint, ForecastRecord, build_points, run_forecasts
from agent.broker import Broker
from agent.config import REPORTS_DIR, Config, load_config, load_secrets
from agent.data import Article
from agent.forecast import load_model
from agent.news import NewsSource, news_count_covariate, news_score_covariate
from agent.news_backtest import NEWS_CACHE_PATH, Covariates, load_articles
from agent.store import ArticleScore, Store

logger = logging.getLogger(__name__)

TUNING_END = datetime(2026, 8, 30, tzinfo=UTC)
CONFIRM_START = datetime(2026, 9, 1, tzinfo=UTC)
WINDOWS = (6, 12, 24)
VOLATILITY_BARS = 24
SURPRISE_BARS = 35
BOOTSTRAPS = 5000
CORRECTED_LEVEL = 0.983  # 95% corrected for the 3 hypotheses
MIN_SYMBOLS_WITH_SIGN = 3
SEED = 20261114

Floats = NDArray[np.float64]


@dataclass(frozen=True)
class Row:
    """Everything known at one evaluation point, and what happened next."""

    symbol: str
    time: datetime
    day: int
    volatility: float
    abs_move: float
    count: dict[int, float]
    abs_sentiment: dict[int, float]
    lower: float
    upper: float
    actual: float


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float

    def excludes_zero(self, sign: int) -> bool:
        return self.low > 0 if sign > 0 else self.high < 0

    def text(self) -> str:
        return f"{self.estimate:+.4f} [{self.low:+.4f}, {self.high:+.4f}]"


# --- features ------------------------------------------------------------------------------


def realized_volatility(values: Floats) -> float:
    returns = np.diff(np.log(values))[-VOLATILITY_BARS:]
    return float(np.nanstd(returns)) if np.isfinite(returns).any() else 0.0


def build_rows(
    records: list[ForecastRecord],
    articles: dict[str, list[Article]],
    scores: dict[str, dict[int, ArticleScore]],
) -> list[Row]:
    rows: list[Row] = []
    for r in records:
        p, symbol = r.point, r.forecast.symbol
        times = [a.created_at for a in articles[symbol]]
        scored = [a for a in articles[symbol] if a.id in scores.get(symbol, {})]
        count = {
            w: float(news_count_covariate(p.series.slot_starts, times, w)[-1]) for w in WINDOWS
        }
        sentiment = {w: _last_abs_sentiment(p, scored, scores.get(symbol, {}), w) for w in WINDOWS}
        rows.append(
            Row(
                symbol=symbol,
                time=p.time,
                day=p.time.toordinal(),
                volatility=realized_volatility(p.series.values),
                abs_move=abs(float(np.log(p.actual / r.forecast.last_price))),
                count=count,
                abs_sentiment=sentiment,
                lower=r.forecast.lower[-1],
                upper=r.forecast.upper[-1],
                actual=p.actual,
            )
        )
    return rows


def _last_abs_sentiment(
    point: EvalPoint, scored: list[Article], scores: dict[int, ArticleScore], window: int
) -> float:
    if not scored:
        return 0.0
    value = news_score_covariate(
        point.series.slot_starts,
        [a.created_at for a in scored],
        [scores[a.id] for a in scored],
        window,
    )[-1]
    return 0.0 if np.isnan(value) else abs(float(value))


def surprise_covariate(count_series: Floats) -> Floats:
    """Count minus the mean of the previous SURPRISE_BARS values of the same count series."""
    previous = np.array(
        [
            count_series[max(0, k - SURPRISE_BARS) : k].mean() if k else 0.0
            for k in range(len(count_series))
        ]
    )
    return np.asarray(count_series - previous, dtype=np.float64)


def variant_covariates(
    name: str,
    points: list[EvalPoint],
    articles: dict[str, list[Article]],
    scores: dict[str, dict[int, ArticleScore]],
) -> Covariates:
    kind, window = name.rsplit("_", 1)
    w = int(window)
    out: Covariates = {}
    for p in points:
        symbol = p.series.symbol
        if kind == "count":
            times = [a.created_at for a in articles[symbol]]
            out[(symbol, p.time)] = news_count_covariate(p.series.slot_starts, times, w)
        elif kind == "surprise":
            times = [a.created_at for a in articles[symbol]]
            counts = news_count_covariate(p.series.slot_starts, times, w)
            out[(symbol, p.time)] = surprise_covariate(counts)
        else:
            kept = [a for a in articles[symbol] if a.id in scores[symbol]]
            out[(symbol, p.time)] = np.abs(
                news_score_covariate(
                    p.series.slot_starts,
                    [a.created_at for a in kept],
                    [scores[symbol][a.id] for a in kept],
                    w,
                )
            )
    return out


# --- statistics ----------------------------------------------------------------------------


def day_bootstrap(
    days: NDArray[np.int64],
    statistic: Callable[[NDArray[np.int64]], float],
    rng: np.random.Generator,
) -> Interval:
    """Bootstrap by calendar day, because consecutive points overlap in time."""
    unique = np.unique(days)
    groups = [np.flatnonzero(days == d) for d in unique]
    draws = np.empty(BOOTSTRAPS)
    for i in range(BOOTSTRAPS):
        chosen = rng.integers(0, len(groups), len(groups))
        draws[i] = statistic(np.concatenate([groups[j] for j in chosen]))
    alpha = (1 - CORRECTED_LEVEL) / 2
    low, high = np.nanpercentile(draws, [100 * alpha, 100 * (1 - alpha)])
    return Interval(statistic(np.arange(len(days))), float(low), float(high))


def standardizer(rows: list[Row], value: Callable[[Row], float]) -> dict[str, tuple[float, float]]:
    """Per-symbol mean and standard deviation of a feature, on the given rows."""
    stats: dict[str, tuple[float, float]] = {}
    for symbol in sorted({r.symbol for r in rows}):
        values = np.array([value(r) for r in rows if r.symbol == symbol])
        stats[symbol] = (float(values.mean()), float(values.std()) or 1.0)
    return stats


def zscore(
    rows: list[Row], value: Callable[[Row], float], stats: dict[str, tuple[float, float]]
) -> Floats:
    return np.array([(value(r) - stats[r.symbol][0]) / stats[r.symbol][1] for r in rows])


def ols(x: Floats, y: Floats) -> Floats:
    design = np.column_stack([np.ones(len(y)), x])
    return np.asarray(np.linalg.lstsq(design, y, rcond=None)[0], dtype=np.float64)


def news_t_stat(x: Floats, y: Floats) -> float:
    design = np.column_stack([np.ones(len(y)), x])
    beta = ols(x, y)
    residual = y - design @ beta
    sigma2 = float(residual @ residual) / max(len(y) - design.shape[1], 1)
    covariance = sigma2 * np.linalg.pinv(design.T @ design)
    return float(beta[-1] / np.sqrt(covariance[-1, -1]))


# --- H1: news volume or sentiment and the size of the next move ----------------------------


@dataclass(frozen=True)
class H1Variant:
    name: str
    feature: Callable[[Row], float]


def _log_count(window: int) -> Callable[[Row], float]:
    return lambda r: float(np.log1p(r.count[window]))


def _abs_sentiment(window: int) -> Callable[[Row], float]:
    return lambda r: r.abs_sentiment[window]


def _on_subset(
    idx: NDArray[np.int64], statistic: Callable[[NDArray[np.int64]], float]
) -> Callable[[NDArray[np.int64]], float]:
    """The statistic on the points `idx`; its argument is a resample of positions within `idx`."""
    return lambda positions: statistic(idx[positions])


def h1_variants() -> list[H1Variant]:
    return [H1Variant(f"count_{w}", _log_count(w)) for w in WINDOWS] + [
        H1Variant(f"abs_sentiment_{w}", _abs_sentiment(w)) for w in WINDOWS
    ]


def _h1_matrix(
    rows: list[Row], variant: H1Variant, stats: dict[str, dict[str, tuple[float, float]]]
) -> tuple[Floats, Floats]:
    vol = zscore(rows, lambda r: r.volatility, stats["vol"])
    news = zscore(rows, variant.feature, stats["news"])
    y = zscore(rows, lambda r: r.abs_move, stats["move"])
    return np.column_stack([vol, news]), y


def _h1_stats(rows: list[Row], variant: H1Variant) -> dict[str, dict[str, tuple[float, float]]]:
    return {
        "vol": standardizer(rows, lambda r: r.volatility),
        "news": standardizer(rows, variant.feature),
        "move": standardizer(rows, lambda r: r.abs_move),
    }


def run_h1(tuning: list[Row], confirm: list[Row], rng: np.random.Generator) -> list[str]:
    lines = ["## H1: news and the size of the next move", ""]
    lines += [
        "Tuning period, every variant (t-statistic of the news coefficient, "
        "controlling for volatility):",
        "",
    ]
    lines += [
        "| Variant | Symbols | Points | News coefficient | t-statistic |",
        "| --- | --- | --- | --- | --- |",
    ]
    best: tuple[float, H1Variant] | None = None
    for variant in h1_variants():
        rows = [r for r in tuning if variant.name.startswith("count") or r.symbol != "GLD"]
        x, y = _h1_matrix(rows, variant, _h1_stats(rows, variant))
        t = news_t_stat(x, y)
        lines.append(
            f"| {variant.name} | {len({r.symbol for r in rows})} | {len(rows)} "
            f"| {ols(x, y)[-1]:+.3f} | {t:+.2f} |"
        )
        if best is None or t > best[0]:
            best = (t, variant)
    assert best is not None
    chosen = best[1]
    lines += ["", f"Selected on tuning: **{chosen.name}**.", ""]
    keep = (lambda r: True) if chosen.name.startswith("count") else (lambda r: r.symbol != "GLD")
    fit_rows = [r for r in tuning if keep(r)]
    test_rows = [r for r in confirm if keep(r)]
    stats = _h1_stats(fit_rows, chosen)
    x_fit, y_fit = _h1_matrix(fit_rows, chosen, stats)
    beta_vol, beta_full = ols(x_fit[:, :1], y_fit), ols(x_fit, y_fit)
    x_test, y_test = _h1_matrix(test_rows, chosen, stats)
    days = np.array([r.day for r in test_rows])

    def coefficient(idx: NDArray[np.int64]) -> float:
        return float(ols(x_test[idx], y_test[idx])[-1])

    def mse_gain(idx: NDArray[np.int64]) -> float:
        e_vol = y_test[idx] - (beta_vol[0] + x_test[idx, :1] @ beta_vol[1:])
        e_full = y_test[idx] - (beta_full[0] + x_test[idx] @ beta_full[1:])
        return float(np.mean(e_vol**2 - e_full**2))

    coef = day_bootstrap(days, coefficient, rng)
    gain = day_bootstrap(days, mse_gain, rng)
    lines += [
        f"Confirmation ({len(test_rows)} points), 98.3% day-bootstrap intervals:",
        "",
        f"- News coefficient, controlling for volatility (standardized units): {coef.text()}",
        f"- Out-of-sample squared-error gain of volatility + news over volatility only "
        f"(fitted on tuning, standardized units): {gain.text()}",
        "",
        "| Symbol | Points | News coefficient |",
        "| --- | --- | --- |",
    ]
    positive = 0
    for symbol in sorted({r.symbol for r in test_rows}):
        idx = np.flatnonzero([r.symbol == symbol for r in test_rows])
        per_symbol = day_bootstrap(days[idx], _on_subset(idx, coefficient), rng)
        positive += per_symbol.estimate > 0
        lines.append(f"| {symbol} | {len(idx)} | {per_symbol.text()} |")
    clear = coef.excludes_zero(+1) and positive >= MIN_SYMBOLS_WITH_SIGN
    lines += [
        "",
        f"**H1 verdict: {'clear effect' if clear else 'no clear effect'}** "
        f"({positive} symbols with a positive coefficient).",
        "",
    ]
    return lines


# --- H2: range too narrow when news volume is high ---------------------------------------


def outside(rows: list[Row]) -> Floats:
    return np.array([float(r.actual < r.lower or r.actual > r.upper) for r in rows])


def high_news(rows: list[Row], window: int, medians: dict[str, float]) -> NDArray[np.bool_]:
    return np.array([r.count[window] > medians[r.symbol] for r in rows])


def share_gap(flags: Floats, high: NDArray[np.bool_], idx: NDArray[np.int64]) -> float:
    miss, up = flags[idx], high[idx]
    if up.all() or not up.any():
        return float("nan")
    return float(miss[up].mean() - miss[~up].mean())


def run_h2(tuning: list[Row], confirm: list[Row], rng: np.random.Generator) -> list[str]:
    lines = ["## H2: the 10%-90% range is too narrow when news volume is high", ""]
    lines += ["Tuning period, every window (share outside the range, high minus low news):", ""]
    lines += [
        "| Window (bars) | Outside, high news | Outside, low news | Difference |",
        "| --- | --- | --- | --- |",
    ]
    best_window, best_gap = WINDOWS[0], -np.inf
    for w in WINDOWS:
        medians = _medians(tuning, w)
        high = high_news(tuning, w, medians)
        flags = outside(tuning)
        gap = share_gap(flags, high, np.arange(len(tuning)))
        lines.append(f"| {w} | {flags[high].mean():.1%} | {flags[~high].mean():.1%} | {gap:+.1%} |")
        if gap > best_gap:
            best_window, best_gap = w, gap
    lines += [
        "",
        f"Selected on tuning: **{best_window} bars** (threshold: tuning median per symbol).",
        "",
    ]
    medians = _medians(tuning, best_window)
    high = high_news(confirm, best_window, medians)
    flags = outside(confirm)
    days = np.array([r.day for r in confirm])

    def high_minus_low(idx: NDArray[np.int64]) -> float:
        return share_gap(flags, high, idx)

    overall = day_bootstrap(days, high_minus_low, rng)
    lines += [
        f"Confirmation ({len(confirm)} points): outside the range {flags[high].mean():.1%} "
        "with high news "
        f"(n={high.sum()}) against {flags[~high].mean():.1%} with low news (n={(~high).sum()}); "
        f"nominal 20%.",
        f"- Difference high minus low, 98.3% day-bootstrap interval: {overall.text()}",
        "",
        "| Symbol | High n | Low n | Outside, high | Outside, low | Difference |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    positive = 0
    for symbol in sorted({r.symbol for r in confirm}):
        idx = np.flatnonzero([r.symbol == symbol for r in confirm])
        up = high[idx]
        gap = share_gap(flags, high, idx)
        positive += bool(gap > 0)
        low_text = f"{flags[idx][~up].mean():.1%}" if (~up).any() else "n/a"
        high_text = f"{flags[idx][up].mean():.1%}" if up.any() else "n/a"
        lines.append(
            f"| {symbol} | {up.sum()} | {(~up).sum()} | {high_text} | {low_text} | {gap:+.1%} |"
        )
    clear = overall.excludes_zero(+1) and positive >= MIN_SYMBOLS_WITH_SIGN
    lines += [
        "",
        f"**H2 verdict: {'clear effect' if clear else 'no clear effect'}** "
        f"({positive} symbols with more misses in high-news points).",
        "",
    ]
    return lines


def _medians(rows: list[Row], window: int) -> dict[str, float]:
    return {
        s: float(np.median([r.count[window] for r in rows if r.symbol == s]))
        for s in sorted({r.symbol for r in rows})
    }


# --- H3: finer covariates through Timestral ------------------------------------------------

H3_VARIANTS = (
    "count_12",
    "count_24",
    "surprise_6",
    "abs_sentiment_6",
    "abs_sentiment_12",
    "abs_sentiment_24",
)


def paired_errors(
    baseline: list[ForecastRecord], variant: list[ForecastRecord]
) -> tuple[list[tuple[str, int, bool]], Floats, Floats]:
    """Keys (symbol, day, in confirmation period), baseline errors and variant errors."""
    base = {(r.forecast.symbol, r.point.time): r for r in baseline}
    keys, e_base, e_var = [], [], []
    for r in variant:
        key = (r.forecast.symbol, r.point.time)
        keys.append((key[0], key[1].toordinal(), key[1] >= CONFIRM_START))
        e_base.append(abs(base[key].sample.median - base[key].sample.actual))
        e_var.append(abs(r.sample.median - r.sample.actual))
    return keys, np.array(e_base), np.array(e_var)


def run_h3(
    points: list[EvalPoint],
    baseline: list[ForecastRecord],
    forecaster: TimestralForecaster,
    config: Config,
    articles: dict[str, list[Article]],
    scores: dict[str, dict[int, ArticleScore]],
    rng: np.random.Generator,
) -> list[str]:
    model = config.forecast.model
    lines = ["## H3: finer covariates through Timestral", ""]
    lines += [
        "Tuning period, every variant (paired change of the absolute error vs no covariate; "
        "negative is better):",
        "",
    ]
    lines += ["| Variant | Tuning points | Relative change |", "| --- | --- | --- |"]
    results: dict[str, tuple[list[tuple[str, int, bool]], Floats, Floats]] = {}
    for name in H3_VARIANTS:
        subset = [
            p for p in points if name.startswith(("count", "surprise")) or p.series.symbol in scores
        ]
        covariates = variant_covariates(name, subset, articles, scores)
        records = run_forecasts(subset, forecaster, config, model, covariates)
        results[name] = paired_errors(baseline, records)
        keys, e_base, e_var = results[name]
        tuning = np.array(
            [not k[2] and datetime.fromordinal(k[1]).replace(tzinfo=UTC) < TUNING_END for k in keys]
        )
        change = (e_var[tuning] - e_base[tuning]).mean() / e_base[tuning].mean()
        lines.append(f"| {name} | {tuning.sum()} | {change:+.2%} |")
    chosen = min(results, key=lambda name: _tuning_change(results[name]))
    keys, e_base, e_var = results[chosen]
    confirm = np.array([k[2] for k in keys])
    diff = (e_var - e_base)[confirm]
    days = np.array([k[1] for k in keys])[confirm]
    symbols = np.array([k[0] for k in keys])[confirm]
    base_mean = float(e_base[confirm].mean())

    def mean_change(idx: NDArray[np.int64]) -> float:
        return float(diff[idx].mean())

    overall = day_bootstrap(days, mean_change, rng)
    lines += [
        "",
        f"Selected on tuning: **{chosen}**.",
        "",
        f"Confirmation ({confirm.sum()} points), paired change of the absolute error in USD, "
        f"98.3% day-bootstrap interval: {overall.text()} "
        f"({overall.estimate / base_mean:+.2%} of the baseline error)",
        "",
        "| Symbol | Points | Change of the absolute error (USD) |",
        "| --- | --- | --- |",
    ]
    negative = 0
    for symbol in sorted(set(symbols)):
        idx = np.flatnonzero(symbols == symbol)
        per_symbol = day_bootstrap(days[idx], _on_subset(idx, mean_change), rng)
        negative += per_symbol.estimate < 0
        lines.append(f"| {symbol} | {len(idx)} | {per_symbol.text()} |")
    clear = overall.excludes_zero(-1) and negative >= MIN_SYMBOLS_WITH_SIGN
    lines += [
        "",
        f"**H3 verdict: {'clear effect' if clear else 'no clear effect'}** "
        f"({negative} symbols with a lower error).",
        "",
    ]
    return lines


def _tuning_change(result: tuple[list[tuple[str, int, bool]], Floats, Floats]) -> float:
    keys, e_base, e_var = result
    tuning = np.array(
        [not k[2] and datetime.fromordinal(k[1]).replace(tzinfo=UTC) < TUNING_END for k in keys]
    )
    return float((e_var[tuning] - e_base[tuning]).mean() / e_base[tuning].mean())


# --- main ----------------------------------------------------------------------------------


def split(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    return (
        [r for r in rows if r.time < TUNING_END],
        [r for r in rows if r.time >= CONFIRM_START],
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    broker = Broker(load_secrets(), config.market.feed, config.broker)
    end = datetime.now(UTC)
    bars = broker.fetch_hourly_bars(
        config.market.symbols, end - timedelta(days=config.backtest.history_days), end
    )
    store = Store(NEWS_CACHE_PATH, news_tables=True)
    points = build_points(bars, config)
    articles = load_articles(
        NewsSource(store, broker.fetch_news, config.news), store, points, config.market.symbols
    )
    scores = {s: store.get_scores(s) for s in config.news.scored_symbols}
    model = config.forecast.model
    forecaster = load_model(model)
    records = run_forecasts(points, forecaster, config, model)
    rows = build_rows(records, articles, scores)
    tuning, confirm = split(rows)
    rng = np.random.default_rng(SEED)
    lines = [
        "# News analysis results",
        "",
        "Protocol and hypotheses: `reports/news_analysis_plan.md` (written before this run). "
        f"{len(rows)} points: {len(tuning)} in the tuning period (before {TUNING_END:%Y-%m-%d}), "
        f"{len(confirm)} in the confirmation period (from {CONFIRM_START:%Y-%m-%d}). "
        "Points overlap in time; intervals are day-bootstrap intervals and still optimistic.",
        "",
    ]
    lines += run_h1(tuning, confirm, rng)
    lines += run_h2(tuning, confirm, rng)
    lines += run_h3(points, records, forecaster, config, articles, scores, rng)
    store.close()
    report = "\n".join(lines) + "\n"
    (REPORTS_DIR / "news_analysis.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
