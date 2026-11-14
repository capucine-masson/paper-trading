# Paper Trading Agent

An autonomous agent that manages a small portfolio on an **Alpaca paper account** (no real money).
**Timestral** (a local time-series model) forecasts hourly prices, a **Mistral LLM** proposes
`buy / sell / hold`, and the code decides: client rules and position sizing are computed in plain code
before any order is sent. A static, read-only dashboard shows what the agent did and why.

- Symbols: `SPY, QQQ, AAPL, MSFT, GLD`. One cycle per hour during the US session (GitHub Actions).
- Dashboard: <https://capucine-masson.github.io/paper-trading/> (published by the workflow after each cycle).
- Paper only: the Alpaca URL is a constant in `agent/broker.py`, and the agent refuses to start on a non-paper account.

## How it works

```
Alpaca hourly bars --> data checks --> Timestral forecast --> Mistral LLM --> risk rules + sizing --> Alpaca paper order
 (clock, history)     (gaps, stale)    (median, 10-90%)      (buy/sell/hold)   (pure code, risk.py)         |
                                                                                                           v
                              journal.db (every step, input and output) --> export JSON/CSV --> static dashboard
```

Principles, enforced in code and covered by tests:

- **The LLM proposes, the code decides.** It never gives a quantity or a price; every decision goes through `risk.py`.
- **No order without `--execute`.** Without it the cycle only simulates.
- **No duplicate order.** The `client_order_id` is deterministic and looked up on Alpaca before any submission.
- **No look-ahead.** A decision only uses bars completed before its timestamp.
- **When in doubt, no order.** A failing symbol, a stale series, an invalid forecast or an invalid LLM answer
  produces no order, and never stops the other symbols.
- **Everything is journaled** (forecast, LLM output, risk verdict, order, errors).

### Project structure

| Path | Role |
| --- | --- |
| `agent/config.py` | Settings (`config.toml`) and secrets (`.env`), validated at startup |
| `agent/broker.py` | The only module talking to Alpaca (paper), with bounded retries |
| `agent/data.py` | Hourly series: validation, gaps as `NaN`, freshness |
| `agent/forecast.py` | Timestral forecast and its validation |
| `agent/llm.py` | Prompts and the Mistral call (structured output, one retry, then rejection) |
| `agent/risk.py` | Client rules and position sizing (pure functions) |
| `agent/store.py` | SQLite journal (resumable steps, state) |
| `agent/cycle.py` | One cycle, every external action being a resumable step |
| `agent/run.py` | Command line entry point |
| `agent/export.py` | Journal to JSON/CSV for the dashboard |
| `agent/backtest.py`, `agent/metrics.py` | Walk-forward backtest and evaluation metrics |
| `web/` | Static React dashboard (reads the exported files) |
| `.github/workflows/cycle.yml` | Hourly cycle, journal commit, dashboard deployment |
| `reports/` | Backtest results (`backtest.md`, `backtest.json`, cached LLM outputs) |
| `tests/` | `pytest` suite, no network (Alpaca, Timestral and the LLM are mocked) |

## Quick start

1. `uv sync` (installs Timestral and CPU `torch`).
2. Copy `.env.example` to `.env` and fill `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (paper keys) and `MISTRAL_API_KEY`.
3. Simulated cycle (no order): `uv run python -m agent.run --once`
4. With paper orders: `uv run python -m agent.run --once --execute`

Options:

- `--execute`: send paper orders. Without it the verdict is still journaled, but nothing is sent.
- `--resume`: clear the halted state (manual resume only).
- `--cycle-id ID`: resume a given cycle. The default id is the UTC hour (e.g. `20261116T14`), so re-running
  a cycle within the same hour never duplicates an order or an LLM call.
- `--ignore-market-clock`: simulate while the market is closed (skips the clock and freshness checks).

The first run downloads the Timestral weights (about 111 MB). When the market is closed the cycle is
skipped and says so. Amounts are in USD and times in UTC.

## Rules (`config.toml`)

All values live in `config.toml` (one set of values, one comment per setting). Long only, no leverage,
no short selling, allowed symbols only.

| Setting (`[risk]`) | Value | Meaning | Raise it / lower it |
| --- | --- | --- | --- |
| `enabled` | `true` | Emergency stop: `false` blocks every order | - |
| `allocated_capital` | $10,000 | Capital the agent manages; every limit is computed on it | More / less money at risk |
| `capital_floor` | $8,000 | Equity below it halts the agent (sticky, no automatic selling) | Halts sooner / later |
| `max_daily_loss_pct` | 5 | Daily loss beyond it blocks buys until the next UTC day | Tolerates more / less loss |
| `max_position_pct` | 20 | Maximum size of one symbol | Bigger / smaller bets |
| `max_total_exposure_pct` | 80 | Maximum invested share of the allocated capital | More / less invested |
| `max_orders_per_cycle` | 5 | Maximum orders in one cycle (highest confidence first) | More / fewer trades |
| `min_confidence` | 0.6 | Minimum LLM confidence to act | Fewer / more trades |
| `max_uncertainty` | 0.06 | Maximum forecast interval width (over median) to buy; median 2.9% and 99th percentile 6.3% in the backtest | More / fewer buys |

Position size for a buy: `max_position_pct x allocated_capital x (1 - uncertainty / max_uncertainty)`, capped by
the remaining position and exposure room: the wider the forecast interval, the smaller the position. A `sell`
closes the whole position of that symbol. Agent equity is `allocated_capital` plus the account equity change
since the first run, so the paper account must be used by the agent only.

Other sections: `[market]` (symbols, data feed, history, freshness, gaps), `[forecast]` (model, context, horizon),
`[llm]` (model, temperature, timeout, retries), `[broker]` (retries), `[backtest]` (evaluation settings).

## Emergency stop

| I want to... | Do this | Effect |
| --- | --- | --- |
| Block every order immediately | Set `enabled = false` in `config.toml` and push | From the next cycle, every verdict is rejected ("emergency stop"). Forecasts and LLM decisions are still journaled. |
| Stop the agent completely | GitHub: Actions > cycle > `...` > Disable workflow | No cycle runs at all. Re-enable to restart. |
| Resume after a halt | GitHub: Actions > cycle > Run workflow, tick `resume` (locally: `--resume`) | Clears the sticky halted state. If equity is still below the floor, the agent halts again. |

The agent **halts by itself** when its equity falls below `capital_floor`. The halted state is sticky: it
survives between runs and only a manual resume clears it. Neither the emergency stop nor the halted state
sells positions or cancels orders (the agent never liquidates automatically): close a position or cancel an
open order by hand in the Alpaca paper dashboard if needed.

## Automation (GitHub Actions)

`.github/workflows/cycle.yml` runs `agent.run --once --execute` at minute 7 of every hour from 14:00 to 20:00 UTC,
Monday to Friday. Whether the market is open comes from the Alpaca clock, not from the cron. It can also be
started by hand (Actions > cycle > Run workflow).

Setup, once:

1. Add the repository secrets `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` and `MISTRAL_API_KEY` (`HF_TOKEN` is optional).
2. Settings > Pages > Source: **GitHub Actions**.

After every run, even a failed one, the workflow exports the dashboard data and commits `journal.db` and
`web/public/data/`, then builds and deploys the dashboard. The run turns red when a symbol fails. One cycle
runs at a time (`concurrency`). Before pushing your own commits, run `git pull --rebase origin main`: the
workflow pushes too. Do not run `--execute` from your own machine while the workflow is active, two journals
would diverge.

## Dashboard and export

`uv run python -m agent.export` turns `journal.db` into files in `web/public/data/`: JSON for the dashboard
(status and metrics, equity curve and positions, decisions with their forecast path) plus three CSV files meant
for Excel (UTF-8 with BOM, UTC timestamps): `trades.csv` (timestamp, symbol, side, quantity, fill price, status),
`decisions.csv` (timestamp, symbol, action, risk verdict, risk reason, LLM reasoning) and `equity.csv`
(timestamp, equity, buy_and_hold). It also copies `reports/backtest.json` there when the report exists. The
dashboard (`web/`, React + Vite + TypeScript) is static and read-only: it only reads these files, and no button
acts on the agent.

Three tabs, light or dark theme (moon/sun button, follows the device, remembered in `localStorage`):

- **Overview**, one screen without scrolling: PnL, return (with the buy and hold's), max drawdown and orders
  sent; positions with their weight, exposure and cash; last run; the three CSV downloads;
  and a line saying how much of the Alpaca paper account the agent manages (the account size is the equity read
  from Alpaca at the last cycle that ran). The chart has one point per cycle (no gap for nights and weekends).
  With all symbols it shows the agent's portfolio value, a dashed line at the starting value, a marker where
  orders were placed (symbol, action, price) and a grey buy and hold reference line; the capital floor appears
  only when the value gets close to it. With one symbol it shows that symbol's price and only its order markers
  (action, quantity, price), with no buy and hold line since the price line already is its buy and hold.
  The symbol and period (1D, 3D, All) apply to the chart only and live in the URL.

  **The buy and hold is a reference, not a rival strategy.** It starts at the agent's first cycle with the
  allocated capital split equally across the configured symbols (fractional quantities), is bought once at that
  cycle's prices, never rebalanced, with no costs, and is valued at each cycle with the same hourly closes the
  agent uses. It is always fully invested, while the agent may hold cash. If a symbol has no price at a cycle,
  that point stays empty (nothing is filled in).
- **Decisions**: one card per decision with the price, the position before, the Timestral fan chart (median and
  10%-90% band), the LLM rationale, the guardrail verdict (accepted, reduced, blocked or no order, with the
  reason) and the Alpaca order with its fill price. A buy is "reduced" when the position or exposure limits cut it
  below the size the forecast uncertainty allows. Fills are read back from Alpaca at the end of each cycle.
- **Forecast quality**: from the backtest, interval calibration (does the announced 80% interval contain 80% of
  real prices?) and error against the naive forecast, overall and per symbol. It says so when Timestral does not
  beat the baseline.

The tab, period and symbol live in the URL (`?tab=decisions&symbol=SPY`) so a view can be shared.

Run locally (port 3030): `cd web`, `pnpm install`, `pnpm dev`. With `pnpm dev`, `/?demo=1` shows sample data to
preview the layout (development only, not part of the published site).

## Journal and resilience

Every step (forecast, LLM output, risk verdict, order, error) is stored in `journal.db` (SQLite) per
`(cycle, symbol, step)`. A step already stored is read back, never redone: re-running a cycle resumes where it
stopped, without a new LLM call or a duplicate order. Network calls are only retried on transient errors (network,
429, 5xx), with an increasing delay and a bounded number of attempts. An invalid LLM answer is retried once, then
rejected (no decision for that symbol); invalid data or an invalid forecast is never retried. After a timeout on an
order, the order is looked up by its `client_order_id` before any new submission.

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

## Known limits

- **Evidence is short.** The decision backtest covers 28 days (59 decision times) and one market regime, with no
  significance test. The +0.13% of the Timestral-only rule on 17 trades is noise.
- **The LLM never bought or sold in the backtest window**, so its buy and sell decisions are covered by tests and
  the risk rules, not by the backtest. The 209M comparison uses 200 points (direction rate is about +/-7 points).
- **Execution is simplified in the backtest:** fills at the next bar close, no spread or slippage. Live orders are
  market orders on a paper account.
- **Data:** Alpaca IEX hourly bars only (a fraction of the volume); overnight and weekend gaps are not filled, so
  consecutive session bars are consecutive steps for Timestral.
- **Equity assumption:** agent equity is derived from the account equity change, so the paper account must be used
  by the agent only.
- **Scheduling:** GitHub may delay or skip a scheduled run. A missed hour is simply a missed cycle.
- **Alpaca calls have no explicit timeout** (`alpaca-py` does not expose one simply); retries and the job timeout
  bound the damage.
- **Not done yet:** news analysis as future covariates for Timestral (planned later).
- Baseline parameters (`rule_signal_threshold`, `momentum_bars`) are fixed in `config.toml`, not tuned.

## Development

`uv run ruff check .`, `uv run mypy .`, `uv run pytest`, and `cd web && pnpm build`.
