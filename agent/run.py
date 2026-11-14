"""CLI entry point: uv run python -m agent.run --once"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

from pydantic import ValidationError

from agent.broker import Broker
from agent.config import load_config, load_secrets
from agent.cycle import SymbolOutcome, run_cycle
from agent.llm import make_client


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper-trading agent")
    parser.add_argument("--once", action="store_true", required=True, help="run a single cycle")
    parser.add_argument(
        "--ignore-market-clock",
        action="store_true",
        help="simulate while the market is closed (skips the clock and freshness checks)",
    )
    args = parser.parse_args()
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        config = load_config()
        secrets = load_secrets()
        broker = Broker(secrets, config.market.feed)
        llm_client = make_client(secrets, config.llm)
    except (ValidationError, OSError, RuntimeError) as error:
        print(f"Startup error: {error}", file=sys.stderr)
        return 1
    cycle_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results = run_cycle(config, broker, llm_client, cycle_id, args.ignore_market_clock)
    if not results:
        print("Market closed: no forecast.")
    for symbol, result in results.items():
        print(_format(symbol, result))
    return 0


def _format(symbol: str, outcome: SymbolOutcome) -> str:
    forecast = outcome.forecast
    if forecast is None:
        return f"{symbol}: no forecast ({outcome.error})"
    line = (
        f"{symbol}: last ${forecast.last_price:,.2f} -> median ${forecast.median[-1]:,.2f} "
        f"[${forecast.lower[-1]:,.2f}, ${forecast.upper[-1]:,.2f}] "
        f"uncertainty {forecast.uncertainty:.2%}"
    )
    decision = outcome.decision
    if decision is None:
        return f"{line}\n  no decision ({outcome.error})"
    return (
        f"{line}\n  {decision.action.upper()} (confidence {decision.confidence:.2f}): "
        f"{decision.rationale}"
    )


if __name__ == "__main__":
    sys.exit(main())
