# Trading agent

Autonomous paper-trading agent: **Timestral** forecasts hourly prices, a **Mistral LLM** will decide
positions (step 2), and orders go to an **Alpaca paper** account (step 3). Paper only.

Current state: step 1 (forecasts only, no LLM, no orders).

## Run

1. `uv sync`
2. Copy `.env.example` to `.env` and fill `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` (paper keys).
3. `uv run python -m agent.run --once`

To simulate while the market is closed, add `--ignore-market-clock` (skips the clock and freshness checks).

The first run downloads the Timestral weights (about 111 MB). When the market is closed, the cycle
prints nothing to forecast. Settings live in `config.toml`.

## Checks

`uv run ruff check .`, `uv run mypy .`, `uv run pytest`
