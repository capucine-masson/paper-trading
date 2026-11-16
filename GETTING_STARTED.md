# Getting started

Everything needed to run the agent from a fresh clone. Paper trading only: no real money is ever used.

## What you need

- **Python 3.12** (`uv` installs it for you if missing) and [`uv`](https://docs.astral.sh/uv/)
- **Node 22** and `pnpm` (only to view the dashboard locally)
- Three free accounts, each giving a key:
  - **Alpaca paper trading** (alpaca.markets): `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` (paper keys)
  - **Mistral AI Studio**: `MISTRAL_API_KEY`
  - **FRED** (fred.stlouisfed.org, My Account > API Keys): `FRED_API_KEY`

## 1. Install

```bash
uv sync --frozen
```

This installs Timestral and the CPU build of `torch`. The first forecast downloads the Timestral weights
(about 111 MB) from Hugging Face.

## 2. Add the keys

```bash
cp .env.example .env
```

Fill the four keys listed above in `.env` (the file is git-ignored). `HF_TOKEN` is optional.

## 3. Run one cycle

```bash
# Simulation: full pipeline, no order is sent (works even when the market is closed)
uv run python -m agent.run --ignore-market-clock

# Real paper orders (only when the US market is open)
uv run python -m agent.run --execute
```

The console prints, for each symbol, the Timestral forecast, the LLM decision and rationale, the risk verdict
and the order. Every step is stored in `journal.db`. Simulated cycles are marked `sim-` and never appear on the
dashboard.

## 4. See the results

```bash
uv run python -m agent.export          # journal.db -> web/public/data/
cd web && pnpm install && pnpm dev     # dashboard on http://localhost:3030
```

The live dashboard, updated after each scheduled cycle, is published to GitHub Pages by the workflow.

## 5. Reproduce the evidence

```bash
uv run python -m agent.backtest            # walk-forward backtest, writes reports/backtest.md
uv run python -m agent.backtest --no-llm   # forecast quality only, no Mistral call
uv run ruff check . && uv run mypy . && uv run pytest
```

The LLM outputs of the backtest are cached in `reports/llm_cache.db`, so re-running it is free.

## Deploy (optional)

The agent runs on its own through `.github/workflows/cycle.yml` (every hour of the US session, Monday to
Friday). The cron is fixed in UTC and set for winter time (15:07 to 20:07 UTC); in summer, change it to
`7 14-19 * * 1-5`. To deploy your own copy:

1. Push the repository to GitHub.
2. Settings > Secrets and variables > Actions: add `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `MISTRAL_API_KEY`
   and `FRED_API_KEY`.
3. Settings > Pages > Source: **GitHub Actions**. Settings > Actions > General: workflow permissions
   "Read and write".
4. Actions > cycle > Run workflow, with `simulate` ticked, to check everything works without any order.

A failed cycle is resumed in place with the same cycle id: journaled steps (LLM output, orders) are read back,
never repeated. To resume by hand, use the workflow inputs `cycle_id` (the cycle to resume) and `resume`
(clears the halted state), or locally `uv run python -m agent.run --execute --cycle-id <id> --resume`.

Settings (symbols, horizon, risk limits) live in `config.toml`. The emergency stop is `enabled = false` there.
