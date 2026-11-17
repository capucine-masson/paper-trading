"""Export the journal as JSON and CSV files read by the static dashboard."""

import csv
import logging
import shutil
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Literal

from pydantic import BaseModel, TypeAdapter

from agent.broker import OrderRecord
from agent.config import BPS_PER_UNIT, EXPORT_DIR, JOURNAL_PATH, REPORTS_DIR, Config, load_config
from agent.forecast import PriceForecast
from agent.llm import Decisions, SymbolDecision
from agent.metrics import buy_and_hold_curve, max_drawdown
from agent.risk import QTY_DECIMALS, PortfolioSnapshot, Verdict
from agent.store import (
    ACCOUNT_EQUITY_KEY,
    HALTED_KEY,
    STEP_DECISIONS,
    STEP_FORECAST,
    STEP_ORDER,
    STEP_PORTFOLIO,
    STEP_VERDICT,
    CycleRow,
    StepRow,
    Store,
    is_simulation,
)

logger = logging.getLogger(__name__)

State = Literal["active", "halted", "stopped"]
VerdictStatus = Literal["accepted", "reduced", "blocked", "no_order"]

BACKTEST_FILE = "backtest.json"
# Excel reads UTF-8 correctly only with a byte order mark.
CSV_ENCODING = "utf-8-sig"
CSV_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FORMULA_PREFIXES = ("=", "+", "-", "@")
USD_DECIMALS = 2
PRICE_DECIMALS = 4
RATIO_DECIMALS = 3


class EquityPoint(BaseModel):
    t: datetime
    cycle_id: str
    equity: float
    buy_and_hold: float | None
    exposure: float
    positions: dict[str, float]
    prices: dict[str, float]


class PositionView(BaseModel):
    symbol: str
    qty: float
    market_value: float
    weight: float


class TradeView(BaseModel):
    t: datetime
    cycle_id: str
    symbol: str
    side: str
    ordered_qty: float | None
    notional: float | None
    qty: float | None
    fill_price: float | None
    status: str


class ForecastPath(BaseModel):
    median: list[float]
    lower: list[float]
    upper: list[float]


class DecisionView(BaseModel):
    t: datetime
    cycle_id: str
    symbol: str
    action: str
    signal_strength: float | None
    size_fraction: float
    rationale: str
    price: float | None
    position_qty: float
    position_value: float
    forecast: ForecastPath | None
    macro: dict[str, float]
    next_event: datetime | None
    event_in_horizon: bool
    verdict: VerdictStatus
    risk_reason: str | None
    order: TradeView | None


class CycleView(BaseModel):
    cycle_id: str
    status: str | None
    detail: str | None
    started_at: datetime


class Metrics(BaseModel):
    equity: float | None = None
    pnl: float | None = None
    total_return: float | None = None
    buy_and_hold_return: float | None = None
    max_drawdown: float | None = None
    exposure: float | None = None
    cash: float | None = None
    estimated_costs: float | None = None


class Status(BaseModel):
    generated_at: datetime
    state: State
    halted_reason: str | None
    last_cycle: CycleView | None
    allocated_capital: float
    symbols: list[str]
    capital_floor: float
    account_size: float | None
    metrics: Metrics


class PortfolioExport(BaseModel):
    points: list[EquityPoint]
    positions: list[PositionView]


class Export(BaseModel):
    status: Status
    portfolio: PortfolioExport
    decisions: list[DecisionView]
    trades: list[TradeView]


def _real_steps(store: Store, name: str) -> list[StepRow]:
    """Journal steps of real cycles: simulated cycles are never exported."""
    return [row for row in store.list_steps(name) if not is_simulation(row.cycle_id)]


def build_export(store: Store, config: Config, now: datetime) -> Export:
    snapshot_rows = _real_steps(store, STEP_PORTFOLIO)
    snapshots = {r.cycle_id: PortfolioSnapshot.model_validate_json(r.result) for r in snapshot_rows}
    forecasts = {
        (r.cycle_id, r.symbol): PriceForecast.model_validate_json(r.result)
        for r in _real_steps(store, STEP_FORECAST)
    }
    trades = [_trade(row) for row in _real_steps(store, STEP_ORDER)]
    allocated = config.risk.allocated_capital
    points = _equity_points(snapshot_rows, snapshots, forecasts, config)
    latest = snapshots[snapshot_rows[-1].cycle_id] if snapshot_rows else None
    cycles = [c for c in store.list_cycles() if not is_simulation(c.cycle_id)]
    last = cycles[-1] if cycles else None
    halted = store.get_state(HALTED_KEY)
    account = store.get_state(ACCOUNT_EQUITY_KEY)
    status = Status(
        generated_at=now,
        state=_state(halted, config),
        halted_reason=halted,
        last_cycle=None if last is None else _cycle_view(last),
        allocated_capital=allocated,
        symbols=config.market.symbols,
        capital_floor=config.risk.capital_floor,
        account_size=None if account is None else float(account),
        metrics=_metrics(points, latest, allocated, _estimated_costs(trades, config)),
    )
    portfolio = PortfolioExport(points=points, positions=_positions(latest))
    decisions = _decisions(store, snapshots, forecasts, trades)
    return Export(status=status, portfolio=portfolio, decisions=decisions, trades=trades)


def _state(halted: str | None, config: Config) -> State:
    if halted is not None:
        return "halted"
    return "active" if config.risk.enabled else "stopped"


def _cycle_view(cycle: CycleRow) -> CycleView:
    return CycleView(
        cycle_id=cycle.cycle_id,
        status=cycle.status,
        detail=cycle.detail,
        started_at=cycle.started_at,
    )


def _trade(row: StepRow) -> TradeView:
    record = OrderRecord.model_validate_json(row.result)
    return TradeView(
        t=record.filled_at or row.created_at,
        cycle_id=row.cycle_id,
        symbol=row.symbol,
        side=record.side,
        ordered_qty=record.qty,
        notional=record.notional,
        qty=record.filled_qty,
        fill_price=record.filled_avg_price,
        status=record.status,
    )


def _equity_points(
    rows: list[StepRow],
    snapshots: dict[str, PortfolioSnapshot],
    forecasts: dict[tuple[str, str], PriceForecast],
    config: Config,
) -> list[EquityPoint]:
    """Prices are the hourly closes the agent saw at each cycle (its forecast input)."""
    prices = [
        {
            symbol: forecast.last_price
            for symbol in config.market.symbols
            if (forecast := forecasts.get((row.cycle_id, symbol))) is not None
        }
        for row in rows
    ]
    exposures = [s.exposure / s.equity for s in (snapshots[row.cycle_id] for row in rows)]
    reference = buy_and_hold_curve(
        prices,
        config.market.symbols,
        config.risk.allocated_capital,
        fmean(exposures) if exposures else 0.0,
    )
    points = []
    for row, cycle_prices, held in zip(rows, prices, reference, strict=True):
        snap = snapshots[row.cycle_id]
        points.append(
            EquityPoint(
                t=row.created_at,
                cycle_id=row.cycle_id,
                equity=snap.equity,
                buy_and_hold=held,
                exposure=snap.exposure,
                positions={s: p.market_value for s, p in snap.positions.items()},
                prices=cycle_prices,
            )
        )
    return points


def _metrics(
    points: list[EquityPoint],
    latest: PortfolioSnapshot | None,
    allocated: float,
    costs: float,
) -> Metrics:
    if latest is None:
        return Metrics()
    pnl = latest.equity - allocated
    reference = [p.buy_and_hold for p in points if p.buy_and_hold is not None]
    return Metrics(
        equity=latest.equity,
        pnl=pnl,
        total_return=pnl / allocated,
        buy_and_hold_return=reference[-1] / reference[0] - 1 if len(reference) >= 2 else None,
        max_drawdown=max_drawdown([p.equity for p in points]),
        exposure=latest.exposure,
        cash=latest.equity - latest.exposure,
        estimated_costs=costs,
    )


def _estimated_costs(trades: list[TradeView], config: Config) -> float:
    """Alpaca paper charges nothing: this applies the backtest cost to the filled amounts."""
    traded = sum(
        t.qty * t.fill_price for t in trades if t.qty is not None and t.fill_price is not None
    )
    return traded * config.backtest.cost_bps / BPS_PER_UNIT


def _positions(latest: PortfolioSnapshot | None) -> list[PositionView]:
    if latest is None:
        return []
    return [
        PositionView(
            symbol=symbol,
            qty=position.qty,
            market_value=position.market_value,
            weight=position.market_value / latest.equity,
        )
        for symbol, position in sorted(latest.positions.items())
    ]


def _verdict_status(action: str, verdict: Verdict | None) -> VerdictStatus:
    if verdict is None or action == "hold":
        return "no_order"
    if not verdict.approved:
        return "blocked"
    return "reduced" if verdict.reduced else "accepted"


def _decisions(
    store: Store,
    snapshots: dict[str, PortfolioSnapshot],
    forecasts: dict[tuple[str, str], PriceForecast],
    trades: list[TradeView],
) -> list[DecisionView]:
    verdicts = {
        (r.cycle_id, r.symbol): Verdict.model_validate_json(r.result)
        for r in _real_steps(store, STEP_VERDICT)
    }
    orders = {(t.cycle_id, t.symbol): t for t in trades}
    return [
        _decision_view(
            row,
            item,
            snapshots.get(row.cycle_id),
            forecasts.get((row.cycle_id, item.symbol)),
            verdicts.get((row.cycle_id, item.symbol)),
            orders.get((row.cycle_id, item.symbol)),
        )
        for row in _real_steps(store, STEP_DECISIONS)
        for item in sorted(
            Decisions.model_validate_json(row.result).decisions, key=lambda d: d.symbol
        )
    ]


def _decision_view(
    row: StepRow,
    item: SymbolDecision,
    snapshot: PortfolioSnapshot | None,
    forecast: PriceForecast | None,
    verdict: Verdict | None,
    order: TradeView | None,
) -> DecisionView:
    decision = item.decision
    held = snapshot.positions.get(item.symbol) if snapshot else None
    path = forecast and ForecastPath(
        median=forecast.median, lower=forecast.lower, upper=forecast.upper
    )
    return DecisionView(
        t=row.created_at,
        cycle_id=row.cycle_id,
        symbol=item.symbol,
        action=decision.action,
        signal_strength=forecast.signal_strength if forecast else None,
        size_fraction=decision.size_fraction,
        rationale=decision.rationale,
        price=forecast.last_price if forecast else None,
        position_qty=held.qty if held else 0.0,
        position_value=held.market_value if held else 0.0,
        forecast=path,
        macro=forecast.macro if forecast else {},
        next_event=forecast.next_event if forecast else None,
        event_in_horizon=forecast.event_in_horizon if forecast else False,
        verdict=_verdict_status(decision.action, verdict),
        risk_reason=verdict.reason if verdict else None,
        order=order,
    )


def write_export(export: Export, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, model in (("status.json", export.status), ("portfolio.json", export.portfolio)):
        (out_dir / name).write_text(model.model_dump_json(indent=2), encoding="utf-8")
    payload = TypeAdapter(list[DecisionView]).dump_json(export.decisions)
    (out_dir / "decisions.json").write_bytes(payload)
    _write_csv(
        out_dir / "trades.csv",
        [
            "timestamp_utc",
            "cycle_id",
            "symbol",
            "side",
            "ordered_qty",
            "notional",
            "filled_qty",
            "fill_price",
            "status",
        ],
        (
            [
                _time(t.t),
                t.cycle_id,
                t.symbol,
                t.side,
                _round(t.ordered_qty, QTY_DECIMALS),
                _round(t.notional, USD_DECIMALS),
                _round(t.qty, QTY_DECIMALS),
                _round(t.fill_price, PRICE_DECIMALS),
                t.status,
            ]
            for t in export.trades
        ),
    )
    _write_csv(
        out_dir / "decisions.csv",
        [
            "timestamp_utc",
            "cycle_id",
            "symbol",
            "action",
            "signal_strength",
            "size_fraction",
            "risk_verdict",
            "risk_reason",
            "llm_reasoning",
        ],
        (
            [
                _time(d.t),
                d.cycle_id,
                d.symbol,
                d.action,
                _round(d.signal_strength, RATIO_DECIMALS),
                d.size_fraction,
                d.verdict,
                _text(d.risk_reason),
                _text(d.rationale),
            ]
            for d in export.decisions
        ),
    )
    allocated = export.status.allocated_capital
    _write_csv(
        out_dir / "equity.csv",
        ["timestamp_utc", "cycle_id", "equity", "pnl", "exposure", "cash", "buy_and_hold"],
        (
            [
                _time(p.t),
                p.cycle_id,
                _round(p.equity, USD_DECIMALS),
                _round(p.equity - allocated, USD_DECIMALS),
                _round(p.exposure, USD_DECIMALS),
                _round(p.equity - p.exposure, USD_DECIMALS),
                _round(p.buy_and_hold, USD_DECIMALS),
            ]
            for p in export.portfolio.points
        ),
    )


def copy_backtest(source: Path, out_dir: Path) -> bool:
    """Publish the latest backtest report next to the journal exports, if one exists."""
    if not source.exists():
        return False
    shutil.copyfile(source, out_dir / BACKTEST_FILE)
    return True


def _time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(CSV_TIME_FORMAT)


def _round(value: float | None, decimals: int) -> float | None:
    return None if value is None else round(value, decimals)


def _text(value: str | None) -> str:
    """Neutralize spreadsheet formulas: LLM text is data, never something Excel should evaluate."""
    if value is None:
        return ""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def _write_csv(path: Path, header: list[str], rows: Iterable[list[object]]) -> None:
    with path.open("w", encoding=CSV_ENCODING, newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    store = Store(JOURNAL_PATH)
    try:
        export = build_export(store, config, datetime.now(UTC))
    finally:
        store.close()
    write_export(export, EXPORT_DIR)
    has_backtest = copy_backtest(REPORTS_DIR / BACKTEST_FILE, EXPORT_DIR)
    logger.info(
        "exported %d decisions, %d trades, %d equity points to %s (backtest report: %s)",
        len(export.decisions),
        len(export.trades),
        len(export.portfolio.points),
        EXPORT_DIR,
        "yes" if has_backtest else "none",
    )


if __name__ == "__main__":
    main()
