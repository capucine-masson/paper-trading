"""CLI entry point: uv run python -m agent.run --once"""

import argparse
import logging
import sys
import time
from datetime import UTC, datetime

from pydantic import ValidationError

from agent.broker import Broker
from agent.config import load_config, load_secrets
from agent.cycle import run_cycle
from agent.forecast import PriceForecast


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
        broker = Broker(load_secrets(), config.market.feed)
    except (ValidationError, OSError, RuntimeError) as error:
        print(f"Startup error: {error}", file=sys.stderr)
        return 1
    cycle_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results = run_cycle(config, broker, cycle_id, args.ignore_market_clock)
    if not results:
        print("Market closed: no forecast.")
    for symbol, result in results.items():
        print(_format(symbol, result))
    return 0


def _format(symbol: str, result: PriceForecast | str) -> str:
    if isinstance(result, str):
        return f"{symbol}: no forecast ({result})"
    return (
        f"{symbol}: last ${result.last_price:,.2f} -> median ${result.median[-1]:,.2f} "
        f"[${result.lower[-1]:,.2f}, ${result.upper[-1]:,.2f}] "
        f"uncertainty {result.uncertainty:.2%}"
    )


if __name__ == "__main__":
    sys.exit(main())
