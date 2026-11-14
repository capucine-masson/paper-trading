"""CLI entry point: uv run python -m agent.run --once [--execute]"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

from pydantic import ValidationError

from agent.broker import Broker
from agent.config import JOURNAL_PATH, load_config, load_secrets
from agent.cycle import STATUS_ERROR, STATUS_SKIPPED, Cycle, CycleReport, SymbolOutcome
from agent.llm import make_client
from agent.store import Store

CYCLE_ID_FORMAT = "%Y%m%dT%H"
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paper-trading agent")
    parser.add_argument("--once", action="store_true", required=True, help="run a single cycle")
    parser.add_argument(
        "--execute", action="store_true", help="send paper orders (otherwise simulate only)"
    )
    parser.add_argument(
        "--resume", action="store_true", help="clear the halted state before running"
    )
    parser.add_argument(
        "--cycle-id", help="resume a given cycle (default: the current UTC hour, e.g. 20261116T14)"
    )
    parser.add_argument(
        "--ignore-market-clock",
        action="store_true",
        help="simulate while the market is closed (skips the clock and freshness checks)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        config = load_config()
        secrets = load_secrets()
        broker = Broker(secrets, config.market.feed, config.broker)
        llm_client = make_client(secrets, config.llm)
    except (ValidationError, OSError, RuntimeError) as error:
        print(f"Startup error: {error}", file=sys.stderr)
        return 1
    store = Store(JOURNAL_PATH)
    if args.resume:
        store.delete_state("halted_reason")
        logger.warning("halted state cleared manually")
    cycle_id = args.cycle_id or datetime.now(UTC).strftime(CYCLE_ID_FORMAT)
    cycle = Cycle(
        config, broker, llm_client, store, cycle_id, args.execute, args.ignore_market_clock
    )
    try:
        report = cycle.run()
    except Exception as error:  # a failing cycle is recorded and reported, never silent
        logger.exception("cycle %s failed", cycle_id)
        store.finish_cycle(cycle_id, STATUS_ERROR, f"{type(error).__name__}: {error}")
        print(f"Cycle {cycle_id} failed: {error}", file=sys.stderr)
        return 1
    finally:
        store.close()
    _print_report(cycle_id, report, args.execute)
    return 0


def _print_report(cycle_id: str, report: CycleReport, execute: bool) -> None:
    mode = "EXECUTE (paper orders)" if execute else "SIMULATION (no order sent)"
    print(f"Cycle {cycle_id} [{mode}]: {report.status}")
    if report.status == STATUS_SKIPPED:
        print(f"  {report.detail}.")
    if report.halted_reason:
        print(f"  HALTED: {report.halted_reason}")
    for symbol, outcome in report.outcomes.items():
        print(_format(symbol, outcome))


def _format(symbol: str, outcome: SymbolOutcome) -> str:
    forecast = outcome.forecast
    if forecast is None:
        return f"{symbol}: no forecast ({outcome.error})"
    lines = [
        f"{symbol}: last ${forecast.last_price:,.2f} -> median ${forecast.median[-1]:,.2f} "
        f"[${forecast.lower[-1]:,.2f}, ${forecast.upper[-1]:,.2f}] "
        f"uncertainty {forecast.uncertainty:.2%}"
    ]
    decision = outcome.decision
    if decision is None:
        lines.append(f"  no decision ({outcome.error})")
        return "\n".join(lines)
    lines.append(
        f"  LLM: {decision.action.upper()} (confidence {decision.confidence:.2f}): "
        f"{decision.rationale}"
    )
    verdict = outcome.verdict
    if verdict is not None:
        lines.append(f"  Risk: {'APPROVED' if verdict.approved else 'REJECTED'}: {verdict.reason}")
    if outcome.order is not None:
        lines.append(f"  Order: {outcome.order.client_order_id} -> {outcome.order.status}")
    elif outcome.error:
        lines.append(f"  Error: {outcome.error}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
