# Trading agent

Autonomous paper-trading agent: **Timestral** forecasts hourly prices, a **Mistral LLM** will decide
positions (step 2), and orders go to an **Alpaca paper** account (step 3). Paper only.

Current state: step 2 (forecasts and LLM decisions, simulated only, no orders).

## Run

1. `uv sync`
2. Copy `.env.example` to `.env` and fill `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (paper keys) and `MISTRAL_API_KEY`.
3. `uv run python -m agent.run --once`

To simulate while the market is closed, add `--ignore-market-clock` (skips the clock and freshness checks).

The first run downloads the Timestral weights (about 111 MB). When the market is closed, the cycle
prints nothing to forecast. Settings live in `config.toml`.

## Checks

`uv run ruff check .`, `uv run mypy .`, `uv run pytest`

## Decisions

For each symbol the LLM returns `buy / sell / hold`, a confidence and a short rationale (validated
structured output, one retry if invalid, then no decision). It never gives a quantity or a price.
