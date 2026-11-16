"""Walk-forward backtest without look-ahead: forecast quality, then decisions against baselines."""

import argparse
import hashlib
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
from mistralai.client import Mistral
from pydantic import BaseModel
from timestral import TimestralForecaster

from agent.broker import Broker
from agent.config import PERCENT, REPORTS_DIR, Config, load_config, load_secrets
from agent.data import BAR_PERIOD, Bar, DataError, PriceSeries, build_series
from agent.forecast import ForecastError, PriceForecast, forecast_symbol, load_model
from agent.llm import (
    SYSTEM_PROMPT,
    Decision,
    Decisions,
    LlmError,
    build_forecast_data,
    build_portfolio_data,
    decide,
    make_client,
)
from agent.metrics import ForecastMetrics, ForecastSample, forecast_metrics, max_drawdown
from agent.risk import Portfolio, Position, apply_to_portfolio, evaluate, halt_reason
from agent.store import CYCLE_SCOPE, Store

logger = logging.getLogger(__name__)

LLM_CACHE_PATH = REPORTS_DIR / "llm_cache.db"
PROGRESS_EVERY = 100
RULE_CONFIDENCE = 1.0

Rule = Callable[["ForecastRecord"], Decision]
Strategy = Callable[[list["ForecastRecord"], Portfolio], dict[str, Decision]]


@dataclass(frozen=True)
class EvalPoint:
    time: datetime
    series: PriceSeries
    actual: float
    fill_price: float


class ForecastPoint(ForecastSample):
    """A forecast sample with its decision time and symbol, for the fan chart."""

    t: datetime
    symbol: str


@dataclass(frozen=True)
class ForecastRecord:
    point: EvalPoint
    forecast: PriceForecast
    seconds: float

    @property
    def sample(self) -> ForecastPoint:
        f = self.forecast
        return ForecastPoint(
            last=f.last_price,
            median=f.median[-1],
            lower=f.lower[-1],
            upper=f.upper[-1],
            actual=self.point.actual,
            t=self.point.time,
            symbol=f.symbol,
        )


class ModelResult(BaseModel):
    label: str
    model: str
    seconds_per_forecast: float
    overall: ForecastMetrics
    per_symbol: dict[str, ForecastMetrics]


class StrategyResult(BaseModel):
    name: str
    final_equity: float
    return_pct: float
    max_drawdown_pct: float
    trades: int
    average_exposure_pct: float


class BacktestReport(BaseModel):
    generated_at: datetime
    symbols: list[str]
    horizon_bars: int
    stride_bars: int
    history_start: datetime
    history_end: datetime
    models: list[ModelResult]
    forecasts: list[ForecastPoint]
    decision_start: datetime | None
    decision_times: int
    llm_failures: int
    strategies: list[StrategyResult]


# --- evaluation points (no look-ahead) -----------------------------------------------------


def build_points(bars: list[Bar], config: Config) -> list[EvalPoint]:
    """Each point only sees bars up to its decision time; the future only gives the targets."""
    symbols = config.market.symbols
    by_symbol = {
        s: sorted((b for b in bars if b.symbol == s), key=lambda b: b.timestamp) for s in symbols
    }
    horizon = config.forecast.horizon
    context = config.forecast.context_length
    points: list[EvalPoint] = []
    for ref_bar in by_symbol[symbols[0]][context - 1 :: config.backtest.stride_bars]:
        for symbol in symbols:
            history = by_symbol[symbol]
            index = next(
                (i for i, b in enumerate(history) if b.timestamp == ref_bar.timestamp), None
            )
            if index is None or index + horizon >= len(history):
                continue
            now = ref_bar.timestamp + BAR_PERIOD
            try:
                series = build_series(symbol, history[: index + 1], context, now, config.market)
            except DataError:
                continue
            points.append(
                EvalPoint(
                    time=now,
                    series=series,
                    actual=history[index + horizon].close,
                    fill_price=history[index + 1].close,
                )
            )
    return points


def subsample(points: list[EvalPoint], per_symbol: int) -> list[EvalPoint]:
    grouped: dict[str, list[EvalPoint]] = defaultdict(list)
    for point in points:
        grouped[point.series.symbol].append(point)
    chosen: list[EvalPoint] = []
    for items in grouped.values():
        step = max(len(items) // per_symbol, 1)
        chosen.extend(items[::step][:per_symbol])
    return chosen


# --- forecast quality ----------------------------------------------------------------------


def run_forecasts(
    points: list[EvalPoint],
    forecaster: TimestralForecaster,
    config: Config,
    model: str,
) -> list[ForecastRecord]:
    forecast_config = config.forecast.model_copy(update={"model": model})
    records: list[ForecastRecord] = []
    for done, point in enumerate(points, start=1):
        started = time.perf_counter()
        try:
            forecast = forecast_symbol(forecaster, point.series, forecast_config)
        except ForecastError as error:
            logger.warning("skipped point: %s", error)
            continue
        records.append(ForecastRecord(point, forecast, time.perf_counter() - started))
        if done % PROGRESS_EVERY == 0:
            logger.info("%s: %d/%d forecasts", model, done, len(points))
    return records


def evaluate_model(label: str, model: str, records: list[ForecastRecord]) -> ModelResult:
    by_symbol: dict[str, list[ForecastSample]] = defaultdict(list)
    for record in records:
        by_symbol[record.forecast.symbol].append(record.sample)
    return ModelResult(
        label=label,
        model=model,
        seconds_per_forecast=float(np.mean([r.seconds for r in records])),
        overall=forecast_metrics([r.sample for r in records]),
        per_symbol={s: forecast_metrics(samples) for s, samples in sorted(by_symbol.items())},
    )


def forecast_points(records: list[ForecastRecord]) -> list[ForecastPoint]:
    """Each point keeps its decision time; the actual price is observed one horizon later."""
    return sorted((r.sample for r in records), key=lambda p: (p.symbol, p.t))


# --- decisions and baselines ---------------------------------------------------------------


def _decision(
    action: Literal["buy", "sell", "hold"], rationale: str, size_fraction: float = 1.0
) -> Decision:
    return Decision(
        action=action, confidence=RULE_CONFIDENCE, size_fraction=size_fraction, rationale=rationale
    )


def cash_rule(_: ForecastRecord) -> Decision:
    return _decision("hold", "Stay in cash.")


def momentum_rule(bars: int) -> Rule:
    def rule(record: ForecastRecord) -> Decision:
        values = record.point.series.values
        past = values[-1 - bars]
        if not np.isfinite(past):
            return _decision("hold", "Past price missing.")
        return _decision("buy" if values[-1] > past else "sell", "Follow the recent move.")

    return rule


def timestral_rule(threshold: float) -> Rule:
    def rule(record: ForecastRecord) -> Decision:
        signal = record.forecast.signal
        if signal > threshold:
            return _decision("buy", "Expected return is large against the interval width.")
        if signal < -threshold:
            return _decision("sell", "Expected loss is large against the interval width.")
        return _decision("hold", "Expected move is small against the interval width.")

    return rule


def equal_weight_buy_and_hold(config: Config) -> Strategy:
    """Buy each symbol once, in equal parts of the exposure limit, then hold."""
    risk = config.risk
    size = min(
        1.0, risk.max_total_exposure_pct / len(config.market.symbols) / risk.max_position_pct
    )

    def strategy(group: list[ForecastRecord], portfolio: Portfolio) -> dict[str, Decision]:
        return {
            record.forecast.symbol: _decision("hold", "Already held.")
            if record.forecast.symbol in portfolio.positions
            else _decision("buy", "Buy once, in equal weight.", size)
            for record in group
        }

    return strategy


def per_symbol(rule: Rule) -> Strategy:
    """A baseline decides each symbol on its own, without looking at the portfolio."""
    return lambda group, _: {record.forecast.symbol: rule(record) for record in group}


class LlmStrategy:
    """The real LLM decision for all symbols at once, cached so a rerun costs nothing.

    The cache key holds the prompt, the time, and the portfolio and forecasts shown to the LLM.
    """

    def __init__(self, client: Mistral, config: Config, cache: Store) -> None:
        self._client = client
        self._config = config
        self._cache = cache
        fingerprint = f"{SYSTEM_PROMPT}|{config.llm.model}|{config.llm.temperature}"
        self._prefix = "bt-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:8]
        self.failures = 0

    def __call__(self, group: list[ForecastRecord], portfolio: Portfolio) -> dict[str, Decision]:
        held = {symbol: position.market_value for symbol, position in portfolio.positions.items()}
        data = build_portfolio_data(
            portfolio.equity, self._config.risk.allocated_capital, portfolio.day_start_equity, held
        )
        forecasts = {record.forecast.symbol: record.forecast for record in group}
        context = data + "".join(build_forecast_data(f) for f in forecasts.values())
        moment = group[0].point.time.isoformat()
        cycle_id = f"{self._prefix}-{moment}-{hashlib.sha256(context.encode()).hexdigest()[:8]}"
        cached = self._cache.get_step(cycle_id, CYCLE_SCOPE, "decisions")
        if cached is not None:
            return _by_symbol(Decisions.model_validate_json(cached))
        try:
            decisions = decide(
                self._client,
                self._config.market.symbols,
                data,
                forecasts.get,
                self._config.llm,
                cycle_id,
            )
        except LlmError as error:
            logger.warning("LLM failed, no order: %s", error)
            self.failures += 1
            return {}
        self._cache.save_step(cycle_id, CYCLE_SCOPE, "decisions", decisions.model_dump_json())
        return _by_symbol(decisions)


def _by_symbol(decisions: Decisions) -> dict[str, Decision]:
    return {item.symbol: item.decision for item in decisions.decisions}


def simulate(
    name: str,
    strategy: Strategy,
    records: list[ForecastRecord],
    config: Config,
    forecast_guard: bool = True,
) -> StrategyResult:
    """Replay decisions through the real rules; fills happen at the next bar close."""
    risk = config.risk
    by_time: dict[datetime, list[ForecastRecord]] = defaultdict(list)
    for record in records:
        by_time[record.point.time].append(record)
    cash = risk.allocated_capital
    quantities: dict[str, float] = {}
    prices: dict[str, float] = {}
    halted: str | None = None
    day = None
    day_start = cash
    curve: list[float] = []
    exposures: list[float] = []
    trades = 0

    def holdings() -> float:
        return sum(q * prices[s] for s, q in quantities.items())

    for moment, group in sorted(by_time.items()):
        for record in group:
            prices[record.forecast.symbol] = record.forecast.last_price
        equity = cash + holdings()
        if moment.date() != day:
            day, day_start = moment.date(), equity
        halted = halted or halt_reason(equity, risk)
        portfolio = Portfolio(
            equity=equity,
            day_start_equity=day_start,
            positions={
                s: Position(qty=q, market_value=q * prices[s]) for s, q in quantities.items()
            },
        )
        decisions = strategy(group, portfolio)
        decided = sorted(
            ((decisions[r.forecast.symbol], r) for r in group if r.forecast.symbol in decisions),
            key=lambda item: item[0].confidence,
            reverse=True,
        )
        approved = 0
        for decision, record in decided:
            verdict = evaluate(
                decision,
                record.forecast,
                portfolio,
                risk,
                config.market.symbols,
                halted,
                approved,
                forecast_guard,
            )
            if not verdict.approved or verdict.order is None:
                continue
            approved += 1
            apply_to_portfolio(portfolio, verdict)
            order, price = verdict.order, record.point.fill_price
            if order.side == "buy" and order.notional is not None:
                cash -= order.notional
                quantities[order.symbol] = (
                    quantities.get(order.symbol, 0.0) + order.notional / price
                )
            else:
                sold = order.qty or 0.0
                cash += sold * price
                quantities[order.symbol] -= sold
                if quantities[order.symbol] <= 0:
                    del quantities[order.symbol]
            trades += 1
        curve.append(cash + holdings())
        exposures.append(holdings() / risk.allocated_capital)
    return StrategyResult(
        name=name,
        final_equity=curve[-1],
        return_pct=(curve[-1] / risk.allocated_capital - 1) * PERCENT,
        max_drawdown_pct=max_drawdown(curve) * PERCENT,
        trades=trades,
        average_exposure_pct=float(np.mean(exposures)) * PERCENT,
    )


# --- report --------------------------------------------------------------------------------


def write_report(report: BacktestReport, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "backtest.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "backtest.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: BacktestReport) -> str:
    lines = [
        f"Symbols: {', '.join(report.symbols)}. Horizon: {report.horizon_bars} hourly bars. "
        f"History {report.history_start:%Y-%m-%d} to {report.history_end:%Y-%m-%d}, "
        f"one evaluation point every {report.stride_bars} bars.",
        "",
        "### Forecast quality",
        "",
        "| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage "
        "| Mean width | Seconds per forecast |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in report.models:
        o = m.overall
        lines.append(
            f"| {m.label} | {o.n} | {o.mae_ratio:.3f} "
            f"| {o.direction_hit_rate:.1%} (n={o.direction_n}) "
            f"| {o.coverage:.1%} | {o.mean_width:.2%} | {m.seconds_per_forecast:.2f} |"
        )
    lines += ["", "### Decisions against baselines", ""]
    if report.strategies:
        lines += [
            f"Window starts {report.decision_start:%Y-%m-%d}, "
            f"{report.decision_times} decision times, "
            f"{report.llm_failures} LLM failures (no order at that time).",
            "",
            "| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for s in report.strategies:
            lines.append(
                f"| {s.name} | {s.return_pct:+.2f}% | {s.max_drawdown_pct:.2f}% | {s.trades} "
                f"| {s.average_exposure_pct:.1f}% | ${s.final_equity:,.2f} |"
            )
    else:
        lines.append("Not run.")
    return "\n".join(lines) + "\n"


def run_backtest(
    config: Config, bars: list[Bar], llm_client: Mistral | None, compare: bool
) -> BacktestReport:
    points = build_points(bars, config)
    logger.info("%d evaluation points", len(points))
    main_model = config.forecast.model
    records = run_forecasts(points, load_model(main_model), config, main_model)
    models = [evaluate_model("Main model, all points", main_model, records)]
    if compare:
        subset = subsample(points, config.backtest.compare_points_per_symbol)
        chosen = {(p.series.symbol, p.time) for p in subset}
        main_subset = [r for r in records if (r.forecast.symbol, r.point.time) in chosen]
        other = config.backtest.compare_model
        other_records = run_forecasts(subset, load_model(other), config, other)
        models.append(evaluate_model("Main model, comparison subset", main_model, main_subset))
        models.append(evaluate_model("Larger model, comparison subset", other, other_records))
    stamps = [b.timestamp for b in bars]
    window_start = max(r.point.time for r in records) - timedelta(
        days=config.backtest.decision_window_days
    )
    window = [r for r in records if r.point.time >= window_start]
    strategies: list[StrategyResult] = []
    llm_failures = 0
    if llm_client is not None and window:
        LLM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        llm = LlmStrategy(llm_client, config, Store(LLM_CACHE_PATH))
        # Pure baselines ignore the forecast, so the no-buy-against-the-forecast rule skips them.
        named: list[tuple[str, Strategy, bool]] = [
            ("Cash (never trade)", per_symbol(cash_rule), False),
            ("Equal-weight buy and hold", equal_weight_buy_and_hold(config), False),
            ("Momentum rule", per_symbol(momentum_rule(config.backtest.momentum_bars)), False),
            (
                "Timestral-only rule",
                per_symbol(timestral_rule(config.backtest.rule_signal_threshold)),
                True,
            ),
            ("Timestral + LLM (the agent)", llm, True),
        ]
        strategies = [simulate(n, strategy, window, config, guard) for n, strategy, guard in named]
        llm_failures = llm.failures
    return BacktestReport(
        generated_at=datetime.now(UTC),
        symbols=config.market.symbols,
        horizon_bars=config.forecast.horizon,
        stride_bars=config.backtest.stride_bars,
        history_start=min(stamps),
        history_end=max(stamps),
        models=models,
        forecasts=forecast_points(records),
        decision_start=window_start if strategies else None,
        decision_times=len({r.point.time for r in window}),
        llm_failures=llm_failures,
        strategies=strategies,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward backtest")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM and baselines")
    parser.add_argument("--no-compare", action="store_true", help="skip the larger model")
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
    llm_client = None if args.no_llm else make_client(secrets, config.llm)
    report = run_backtest(config, bars, llm_client, not args.no_compare)
    write_report(report, REPORTS_DIR)
    print((REPORTS_DIR / "backtest.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
