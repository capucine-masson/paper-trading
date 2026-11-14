# Trading agent

Autonomous paper-trading agent: **Timestral** forecasts hourly prices, a **Mistral LLM** will decide
positions (step 2), and orders go to an **Alpaca paper** account (step 3). Paper only.

Current state: step 6 (evidence of soundness).

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
| `max_uncertainty` | 0.06 | Maximum forecast interval width (over median) to buy; to be calibrated (median 2.9%, 99th percentile 6.3% in the backtest) | More / fewer buys |

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

## How do we know the decisions are sound?

`uv run python -m agent.backtest` replays the last 180 days of real hourly bars (Alpaca, 5 symbols,
2026-05-18 to 2026-11-13) walk-forward: at each evaluation point (every 3 bars, 1,108 points) the
forecast and the decision only see bars up to that moment. Decisions go through the same `risk.py` rules
and sizing as live, and orders are filled at the next bar close (a test checks that changing the future
never changes a decision input). Full tables: `reports/backtest.md` and `reports/backtest.json`. The LLM
outputs are cached in `reports/llm_cache.db`, so a rerun costs nothing. Use `--no-llm` or `--no-compare`
to skip parts.

**Forecast quality** (horizon: 6 hourly bars; the naive forecast is "the price stays where it is")

| Model | Points | Error vs naive (MAE ratio) | Right direction | 10%-90% coverage | Seconds per forecast |
| --- | --- | --- | --- | --- | --- |
| Timestral-28M, all points | 1,108 | 1.001 | 50.0% | 78.8% (target 80%) | 0.07 |
| Timestral-28M, comparison subset | 200 | 0.992 | 49.0% | 81.0% | 0.07 |
| Timestral-209M, comparison subset | 200 | 1.004 | 45.5% | 78.0% | 0.22 |

- **The intervals are trustworthy**: the 10%-90% interval contains the real price 78.8% of the time. That is
  the quantity the agent uses to size positions and to refuse uncertain buys (`max_uncertainty`).
- **The median has no edge over the naive forecast** on liquid ETFs and large caps at a 6-hour horizon
  (error ratio 1.00, direction 50%). This is expected for such markets and is why the agent should trade rarely.
- **209M is not better than 28M** on the same points and is about 3x slower on CPU, so the agent keeps 28M.

**Decisions against baselines** (last 28 days, 59 decision times, same rules and sizing, $10,000 allocated)

| Strategy | Return | Max drawdown | Trades | Average exposure |
| --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% |
| Buy and hold | -1.01% | 3.28% | 26 | 80.4% |
| Momentum rule | -1.58% | 2.40% | 138 | 35.9% |
| Timestral-only rule (no LLM) | +0.13% | 2.14% | 17 | 33.2% |
| Timestral + LLM (the agent) | +0.00% | 0.00% | 0 | 0.0% |

The LLM answered `hold` every time (0 failures): when the expected move is tiny next to the interval, as
the prompt asks, it does not trade. With no measurable forecast edge, not trading is the sound decision, and
the risk rules cap the damage of any other decision. The agent did not lose money while buy and hold lost 1.01%,
but that is the market falling in this window, not a skill claim.

**Known limits of this evidence**
- Short window: 28 days of decisions (59 times) and about 6 months of forecasts; no significance test,
  and one market regime. The +0.13% of the Timestral-only rule on 17 trades is noise.
- The LLM never bought or sold in the window, so its buy and sell decisions are covered by tests and the
  risk rules, not by this backtest.
- Fills at the next bar close, no spread or slippage; Alpaca IEX bars only (a fraction of the volume).
- The 209M comparison uses 200 points (direction rate is about +/-7 points at this size).
- Baseline parameters (`rule_signal_threshold`, `momentum_bars`) are fixed in `config.toml`, not tuned.
