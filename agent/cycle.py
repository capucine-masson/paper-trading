"""One simulated cycle: data, freshness, forecast per symbol. No LLM, no order."""

import logging
from datetime import UTC, datetime, timedelta

from timestral import TimestralForecaster

from agent.broker import Bar, Broker
from agent.config import Config
from agent.data import DataError, build_series, check_freshness
from agent.forecast import ForecastError, PriceForecast, forecast_symbol, load_model

logger = logging.getLogger(__name__)


def run_cycle(
    config: Config, broker: Broker, cycle_id: str, ignore_market_clock: bool = False
) -> dict[str, PriceForecast | str]:
    """Return a forecast or an error message per symbol; a failing symbol never stops the others."""
    if ignore_market_clock:
        logger.warning("cycle %s: market clock and data freshness checks ignored", cycle_id)
    elif not broker.is_market_open():
        logger.info("cycle %s: market closed, no decision", cycle_id)
        return {}
    now = datetime.now(UTC)
    bars = broker.fetch_hourly_bars(
        config.market.symbols, now - timedelta(days=config.market.history_days), now
    )
    forecaster = load_model(config.forecast.model)
    results: dict[str, PriceForecast | str] = {}
    for symbol in config.market.symbols:
        results[symbol] = _process_symbol(
            config, forecaster, symbol, bars, now, cycle_id, ignore_market_clock
        )
    return results


def _process_symbol(
    config: Config,
    forecaster: TimestralForecaster,
    symbol: str,
    bars: list[Bar],
    now: datetime,
    cycle_id: str,
    ignore_freshness: bool,
) -> PriceForecast | str:
    try:
        series = build_series(symbol, bars, config.forecast.context_length, now, config.market)
        if not ignore_freshness:
            check_freshness(series, now, config.market)
        return forecast_symbol(forecaster, series, config.forecast)
    except (DataError, ForecastError) as error:
        logger.warning("cycle %s: %s", cycle_id, error)
        return str(error)
