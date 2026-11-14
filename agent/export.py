"""Export the journal as JSON and CSV files read by the static dashboard."""

import csv
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from agent.broker import OrderRecord
from agent.config import EXPORT_DIR, JOURNAL_PATH, Config, load_config
from agent.cycle import HALTED_KEY
from agent.forecast import PriceForecast
from agent.llm import Decision
from agent.risk import PERCENT, PortfolioSnapshot, Verdict
from agent.store import Store

logger = logging.getLogger(__name__)

State = Literal["active", "halted", "stopped"]


class EquityPoint(BaseModel):
    t: datetime
    equity: float
    pnl: float
    exposure: float
    positions: dict[str, float]


class PositionView(BaseModel):
    symbol: str
    qty: float
    market_value: float


class DecisionView(BaseModel):
    t: datetime
    cycle_id: str
    symbol: str
    action: str
    confidence: float
    rationale: str
    approved: bool | None
    risk_reason: str | None
    order_status: str | None
    client_order_id: str | None


class ForecastView(BaseModel):
    t: datetime
    cycle_id: str
    symbol: str
    model: str
    last_bar_start: datetime
    horizon_steps: int
    last_price: float
    median: float
    lower: float
    upper: float
    uncertainty: float


class RuleUsage(BaseModel):
    id: str
    label: str
    kind: Literal["max", "min"]
    unit: Literal["usd", "count", "ratio"]
    limit: float
    used: float | None
    breached: bool


class CycleView(BaseModel):
    cycle_id: str
    status: str | None
    detail: str | None
    started_at: datetime
    finished_at: datetime | None


class Status(BaseModel):
    generated_at: datetime
    state: State
    halted_reason: str | None
    last_cycle: CycleView | None
    allocated_capital: float
    equity: float | None
    pnl: float | None
    rules: list[RuleUsage]


class PortfolioExport(BaseModel):
    points: list[EquityPoint]
    positions: list[PositionView]


class Export(BaseModel):
    status: Status
    portfolio: PortfolioExport
    decisions: list[DecisionView]
    forecasts: list[ForecastView]


def build_export(store: Store, config: Config, now: datetime) -> Export:
    snapshots = [
        (row.created_at, PortfolioSnapshot.model_validate_json(row.result))
        for row in store.list_steps("portfolio")
    ]
    forecasts = _forecasts(store)
    decisions = _decisions(store)
    cycles = store.list_cycles()
    last = cycles[-1] if cycles else None
    halted = store.get_state(HALTED_KEY)
    latest = snapshots[-1][1] if snapshots else None
    allocated = config.risk.allocated_capital
    status = Status(
        generated_at=now,
        state=_state(halted, config),
        halted_reason=halted,
        last_cycle=None if last is None else CycleView(**last._asdict()),
        allocated_capital=allocated,
        equity=None if latest is None else latest.equity,
        pnl=None if latest is None else latest.equity - allocated,
        rules=_rules(latest, forecasts, store, config),
    )
    portfolio = PortfolioExport(
        points=[
            EquityPoint(
                t=t,
                equity=s.equity,
                pnl=s.equity - allocated,
                exposure=s.exposure,
                positions={sym: p.market_value for sym, p in s.positions.items()},
            )
            for t, s in snapshots
        ],
        positions=[
            PositionView(symbol=symbol, qty=p.qty, market_value=p.market_value)
            for symbol, p in sorted((latest.positions if latest else {}).items())
        ],
    )
    return Export(status=status, portfolio=portfolio, decisions=decisions, forecasts=forecasts)


def _state(halted: str | None, config: Config) -> State:
    if halted is not None:
        return "halted"
    return "active" if config.risk.enabled else "stopped"


def _forecasts(store: Store) -> list[ForecastView]:
    views = []
    for row in store.list_steps("forecast"):
        f = PriceForecast.model_validate_json(row.result)
        views.append(
            ForecastView(
                t=row.created_at,
                cycle_id=row.cycle_id,
                symbol=f.symbol,
                model=f.model,
                last_bar_start=f.last_bar_start,
                horizon_steps=len(f.median),
                last_price=f.last_price,
                median=f.median[-1],
                lower=f.lower[-1],
                upper=f.upper[-1],
                uncertainty=f.uncertainty,
            )
        )
    return views


def _decisions(store: Store) -> list[DecisionView]:
    verdicts = {
        (r.cycle_id, r.symbol): Verdict.model_validate_json(r.result)
        for r in store.list_steps("verdict")
    }
    orders = {
        (r.cycle_id, r.symbol): OrderRecord.model_validate_json(r.result)
        for r in store.list_steps("order")
    }
    views = []
    for row in store.list_steps("llm"):
        key = (row.cycle_id, row.symbol)
        decision = Decision.model_validate_json(row.result)
        verdict, order = verdicts.get(key), orders.get(key)
        views.append(
            DecisionView(
                t=row.created_at,
                cycle_id=row.cycle_id,
                symbol=row.symbol,
                action=decision.action,
                confidence=decision.confidence,
                rationale=decision.rationale,
                approved=None if verdict is None else verdict.approved,
                risk_reason=None if verdict is None else verdict.reason,
                order_status=None if order is None else order.status,
                client_order_id=None if order is None else order.client_order_id,
            )
        )
    return views


def _rules(
    latest: PortfolioSnapshot | None,
    forecasts: list[ForecastView],
    store: Store,
    config: Config,
) -> list[RuleUsage]:
    risk = config.risk
    capital = risk.allocated_capital
    position_cap = risk.max_position_pct / PERCENT * capital
    exposure_cap = risk.max_total_exposure_pct / PERCENT * capital
    daily_loss_cap = risk.max_daily_loss_pct / PERCENT * capital
    equity = None if latest is None else latest.equity
    daily_loss = None if latest is None else max(0.0, latest.day_start_equity - latest.equity)
    largest = None
    if latest is not None:
        largest = max((p.market_value for p in latest.positions.values()), default=0.0)
    exposure = None if latest is None else latest.exposure
    last_forecasts = (
        [f for f in forecasts if f.cycle_id == forecasts[-1].cycle_id] if forecasts else []
    )
    uncertainty = max((f.uncertainty for f in last_forecasts), default=None)
    verdict_rows = store.list_steps("verdict")
    last_cycle = verdict_rows[-1].cycle_id if verdict_rows else None
    orders = sum(
        Verdict.model_validate_json(r.result).approved
        for r in verdict_rows
        if r.cycle_id == last_cycle
    )

    def rule(
        id_: str,
        label: str,
        kind: Literal["max", "min"],
        unit: Literal["usd", "count", "ratio"],
        limit: float,
        used: float | None,
    ) -> RuleUsage:
        breached = used is not None and (used > limit if kind == "max" else used < limit)
        return RuleUsage(
            id=id_, label=label, kind=kind, unit=unit, limit=limit, used=used, breached=breached
        )

    return [
        rule("capital_floor", "Capital floor", "min", "usd", risk.capital_floor, equity),
        rule("daily_loss", "Daily loss", "max", "usd", daily_loss_cap, daily_loss),
        rule("position", "Largest position", "max", "usd", position_cap, largest),
        rule("exposure", "Total exposure", "max", "usd", exposure_cap, exposure),
        rule("orders", "Orders in last cycle", "max", "count", risk.max_orders_per_cycle, orders),
        rule(
            "uncertainty", "Forecast uncertainty", "max", "ratio", risk.max_uncertainty, uncertainty
        ),
    ]


def write_export(export: Export, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "status.json": export.status,
        "portfolio.json": export.portfolio,
    }
    for name, model in files.items():
        (out_dir / name).write_text(model.model_dump_json(indent=2), encoding="utf-8")
    for name, rows in (("decisions.json", export.decisions), ("forecasts.json", export.forecasts)):
        payload = "[" + ",".join(row.model_dump_json() for row in rows) + "]"
        (out_dir / name).write_text(payload, encoding="utf-8")
    _write_csv(out_dir / "decisions.csv", export.decisions)
    _write_csv(out_dir / "equity.csv", export.portfolio.points, exclude={"positions"})
    _write_csv(out_dir / "forecasts.csv", export.forecasts)


def _write_csv(
    path: Path,
    rows: list[DecisionView] | list[EquityPoint] | list[ForecastView],
    exclude: set[str] | None = None,
) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = [name for name in type(rows[0]).model_fields if name not in (exclude or set())]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump(mode="json", include=set(fields)))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    store = Store(JOURNAL_PATH)
    try:
        export = build_export(store, load_config(), datetime.now(UTC))
    finally:
        store.close()
    write_export(export, EXPORT_DIR)
    logger.info(
        "exported %d decisions, %d forecasts, %d equity points to %s",
        len(export.decisions),
        len(export.forecasts),
        len(export.portfolio.points),
        EXPORT_DIR,
    )


if __name__ == "__main__":
    main()
