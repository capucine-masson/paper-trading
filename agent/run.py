"""CLI entry point: uv run python -m agent.run [--execute]"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

from agent.broker import Broker, BrokerError
from agent.config import CONFIG_ERRORS, JOURNAL_PATH, load_config, load_secrets
from agent.cycle import STATUS_ERROR, STATUS_SKIPPED, Cycle, CycleReport, SymbolOutcome
from agent.llm import make_client
from agent.store import HALTED_KEY, SIMULATION_PREFIX, Store, is_simulation

CYCLE_ID_FORMAT = "%Y%m%dT%H"
EXIT_STARTUP_ERROR = 1  # configuration or credentials: retrying cannot help
EXIT_CYCLE_ERROR = 2  # the cycle ran and failed: the workflow may resume it
STARTUP_ERRORS = (*CONFIG_ERRORS, BrokerError)
logger = logging.getLogger(__name__)


class CliArgs(argparse.Namespace):
    execute: bool
    resume: bool
    cycle_id: str | None
    ignore_market_clock: bool


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="Run one paper-trading cycle")
    parser.add_argument(
        "--execute", action="store_true", help="send paper orders (otherwise simulate only)"
    )
    parser.add_argument(
        "--resume", action="store_true", help="clear the halted state before running"
    )
    parser.add_argument(
        "--cycle-id",
        help="resume a given cycle (default: the current UTC hour, e.g. 20261116T14, "
        "prefixed with sim- when not executing)",
    )
    parser.add_argument(
        "--ignore-market-clock",
        action="store_true",
        help="simulate while the market is closed (skips the clock and freshness checks)",
    )
    args = parser.parse_args(namespace=CliArgs())
    if args.execute and args.ignore_market_clock:
        parser.error("--ignore-market-clock cannot be combined with --execute")
    if args.cycle_id and is_simulation(args.cycle_id) == args.execute:
        rule = "must not start" if args.execute else "must start"
        parser.error(f"--cycle-id {rule} with {SIMULATION_PREFIX}")
    return args


def default_cycle_id(execute: bool, now: datetime) -> str:
    """The UTC hour; a simulation gets a prefix so it can never be mistaken for a real cycle."""
    return ("" if execute else SIMULATION_PREFIX) + now.strftime(CYCLE_ID_FORMAT)


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
    except STARTUP_ERRORS as error:
        print(f"Startup error: {error}", file=sys.stderr)
        return EXIT_STARTUP_ERROR
    store = Store(JOURNAL_PATH)
    if args.resume:
        store.delete_state(HALTED_KEY)
        logger.warning("halted state cleared manually")
    cycle_id = args.cycle_id or default_cycle_id(args.execute, datetime.now(UTC))
    cycle = Cycle(
        config=config,
        broker=broker,
        llm_client=llm_client,
        store=store,
        cycle_id=cycle_id,
        execute=args.execute,
        ignore_market_clock=args.ignore_market_clock,
        fred_api_key=secrets.fred_api_key.get_secret_value(),
    )
    try:
        report = cycle.run()
    except Exception as error:  # a failing cycle is recorded and reported, never silent
        logger.exception("cycle %s failed", cycle_id)
        store.finish_cycle(cycle_id, STATUS_ERROR, f"{type(error).__name__}: {error}")
        print(f"Cycle {cycle_id} failed: {error}", file=sys.stderr)
        return EXIT_CYCLE_ERROR
    finally:
        store.close()
    _print_report(cycle_id, report, args.execute)
    return EXIT_CYCLE_ERROR if report.status == STATUS_ERROR else 0


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
        f"  LLM: {decision.action.upper()} (signal strength {forecast.signal_strength:.0%}, "
        f"size {decision.size_fraction:.0%}): {decision.rationale}"
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
