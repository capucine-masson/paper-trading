# Trading agent

Autonomous paper-trading agent: **Timestral** forecasts hourly prices, a **Mistral LLM** will decide
positions (step 2), and orders go to an **Alpaca paper** account (step 3). Paper only.

Current state: step 5 (read-only dashboard and export).

## Run

1. `uv sync`
2. Copy `.env.example` to `.env` and fill `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (paper keys) and `MISTRAL_API_KEY`.
3. `uv run python -m agent.run --once` (simulation) or add `--execute` to send paper orders

To simulate while the market is closed, add `--ignore-market-clock` (skips the clock and freshness checks).

The first run downloads the Timestral weights (about 111 MB). When the market is closed, the cycle
prints nothing to forecast. Settings live in `config.toml`.

## Checks

`uv run ruff check .`, `uv run mypy .`, `uv run pytest`

## Decisions

For each symbol the LLM returns `buy / sell / hold`, a confidence and a short rationale (validated
structured output, one retry if invalid, then no decision). It never gives a quantity or a price.

## Rules and execution

The LLM only proposes `buy / sell / hold`. The code applies the client rules (`risk.py`), computes the
position size, and only then sends an order. Long only, no leverage, no short selling, allowed symbols only.
All values live in the `[risk]` section of `config.toml`.

| Setting | Value | Meaning | Raise it / lower it |
| --- | --- | --- | --- |
| `enabled` | `true` | Emergency stop: `false` blocks every order | - |
| `allocated_capital` | $10,000 | Capital the agent manages; every limit is computed on it | More / less money at risk |
| `capital_floor` | $8,000 | Equity below it halts the agent (sticky, no automatic selling) | Halts sooner / later |
| `max_daily_loss_pct` | 5 | Daily loss beyond it blocks buys until the next UTC day | Tolerates more / less loss |
| `max_position_pct` | 20 | Maximum size of one symbol | Bigger / smaller bets |
| `max_total_exposure_pct` | 80 | Maximum invested share of the allocated capital | More / less invested |
| `max_orders_per_cycle` | 5 | Maximum orders in one cycle (highest confidence first) | More / fewer trades |
| `min_confidence` | 0.6 | Minimum LLM confidence to act | Fewer / more trades |
| `max_uncertainty` | 0.06 | Maximum forecast interval width (over median) to buy; to be calibrated (observed 2.3-4%) | More / fewer buys |

Position size for a buy: `max_position_pct x allocated_capital x (1 - uncertainty / max_uncertainty)`,
capped by the remaining position and exposure room. A `sell` closes the whole position of that symbol.
Agent equity is `allocated_capital` plus the account equity change since the first run, so the paper
account must be used by the agent only.

## Command options

- `--execute`: send paper orders. Without it the cycle only simulates (the verdict is still journaled).
- `--resume`: clear the halted state (manual resume only).
- `--cycle-id ID`: resume a given cycle. The default id is the UTC hour (e.g. `20261116T14`), so
  re-running a cycle within the same hour never duplicates an order or an LLM call.

## Journal

Every step (forecast, LLM output, risk verdict, order, error) is stored in `journal.db` (SQLite) per
`(cycle, symbol, step)`. A step already stored is read back, never redone. Orders use a deterministic
`client_order_id` (`<cycle>-<symbol>-<side>`) and are looked up on Alpaca before any submission.

## Automation (GitHub Actions)

`.github/workflows/cycle.yml` runs `agent.run --once --execute` at minute 7 of every hour from 14:00 to
20:00 UTC, Monday to Friday. Whether the market is open comes from the Alpaca clock, not from the cron.
It can also be started by hand (Actions > cycle > Run workflow), with a `resume` option that clears the
halted state.

Setup: add the repository secrets `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` and `MISTRAL_API_KEY`
(`HF_TOKEN` is optional). The workflow commits `journal.db` after every run, even a failed one, so the
history and the halted state survive between runs. Do not run `--execute` from your own machine while
the workflow is active: two journals would diverge. The run turns red when a symbol fails.

## Dashboard and export

`uv run python -m agent.export` turns `journal.db` into JSON and CSV files in `web/public/data/`
(status, portfolio curve, positions, decisions, forecasts, rules usage). The workflow runs it after
every cycle and commits the files with the journal.

The dashboard (`web/`, React + Vite + TypeScript) is static and read-only: it only reads these files.
It shows the agent state (active, halted, emergency stop) with the reason, the last cycle status,
portfolio value, positions, latest decisions with the LLM rationale and the risk verdict, forecasts per
symbol, rules with their usage (e.g. exposure $1,000.00 of $8,000.00) and downloads of the exports.
Period (1 day, 3 days, all), symbol and theme are display controls only: period and symbol live in the
URL (`?period=3d&symbol=SPY`), the theme follows the device and is remembered in `localStorage`.

Run locally (port 3030): `cd web`, `pnpm install`, `pnpm dev`. Check: `pnpm build`.

Publication: the workflow builds `web/` and deploys it to GitHub Pages after every cycle. One-time
setup: Settings > Pages > Source: **GitHub Actions**.
