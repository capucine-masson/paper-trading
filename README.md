# Paper Trading Agent

An autonomous agent that manages a small portfolio on an **Alpaca paper account** (no real money).
A **Mistral LLM** sees the portfolio and calls **Timestral** (a local time-series model) as a tool to get an
hourly price forecast for each symbol, then proposes `buy / sell / hold` and how much of the maximum position it
wants, for every symbol, in one conversation. The code decides: dollars, caps and risk rules are computed in
plain code before any order is sent. A static, read-only dashboard shows
what the agent did and why. Paper trading only, not investment advice.

- Symbols: `SPY, QQQ, XLE, XLF, XLU, TLT, GLD, EEM` (the ETFs suggested by the brief). One cycle per hour during the US session (GitHub Actions).
- Dashboard: <https://capucine-masson.github.io/paper-trading/> (published by the workflow after each cycle).
- Paper only: the Alpaca URL is a constant in `agent/broker.py`, and the agent refuses to start on a non-paper account.

## How it works

```
Alpaca hourly bars --> data checks --> Mistral LLM <--tool call--> Timestral forecast --> risk rules + sizing --> Alpaca paper order
 (clock, history)     (gaps, stale)  (portfolio, 1 decision/symbol) (median, 10-90%)      (pure code, risk.py)         |
                                                                                                                       v
                              journal.db (every step, input and output) --> export JSON/CSV --> static dashboard
```

Principles, enforced in code and covered by tests:

- **The LLM proposes, the code decides.** It sees the portfolio (equity, cash, positions, results), calls the
  Timestral tool, then gives for each symbol an action, a confidence and a size as a share of the maximum
  position (`size_fraction`, 0 to 1). It never gives a quantity or a price: the code converts the share to
  dollars, caps it and runs every decision through `risk.py`. The code runs the tool itself, only for allowed
  symbols; a bad tool call gets an error text, and a decision for a symbol without forecast is dropped.
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
| `agent/llm.py` | Prompts and the Mistral conversation: tool call, then structured decisions (one retry, then rejection) |
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
- `--ignore-market-clock`: simulate while the market is closed (skips the clock and freshness checks). It cannot
  be combined with `--execute`.

**Simulated cycles** (no `--execute`) are stored in the journal like any other, with the same steps (portfolio,
forecast, LLM output, verdict) but never an order, under an id prefixed with `sim-` (e.g. `sim-20261116T14`).
They are excluded from the export, so a test run never shows up on the dashboard (decisions, equity curve,
last run) and cannot be mistaken for a real decision. They only appear in the console and in `journal.db`.

The first run downloads the Timestral weights (about 111 MB). When the market is closed the cycle is
skipped and says so. Amounts are in USD and times in UTC.

## Rules (`config.toml`)

All values live in `config.toml` (one set of values, one comment per setting). Long only, no leverage,
no short selling, allowed symbols only.

| Setting (`[risk]`) | Value | Meaning | Raise it / lower it |
| --- | --- | --- | --- |
| `enabled` | `true` | Emergency stop: `false` blocks every order | - |
| `allocated_capital` | $10,000 | Capital the agent manages; every limit is computed on it | More / less money at risk |
| `capital_floor` | $5,000 | Equity below it halts the agent (sticky, no automatic selling) | Halts sooner / later |
| `max_daily_loss_pct` | 10 | Daily loss beyond it blocks buys until the next UTC day | Tolerates more / less loss |
| `max_position_pct` | 25 | Maximum size of one symbol | Bigger / smaller bets |
| `max_total_exposure_pct` | 90 | Maximum invested share of the allocated capital | More / less invested |
| `max_orders_per_cycle` | 5 | Maximum orders in one cycle (highest confidence first) | More / fewer trades |
| `min_confidence` | 0.5 | Minimum LLM confidence to act | Fewer / more trades |
| `max_uncertainty` | 0.08 | Maximum forecast interval width (over median) to buy; median 2.3%, 99th percentile 4.3% and maximum 5.6% in the backtest, so it only binds in exceptional conditions | More / fewer buys |

**No buy against the forecast.** Besides these limits, `risk.py` refuses any buy when Timestral's expected return
over the horizon is not positive: the LLM judges freely, the code only blocks what contradicts the forecast. (The
pure baselines of the backtest skip this rule, since they ignore the forecast.)

Position size for a buy: `max_position_pct x allocated_capital x min(size_fraction, 1 - uncertainty / max_uncertainty)`,
capped by the remaining position and exposure room. The LLM chooses `size_fraction`; the code never lets a wide
forecast interval be sized up: the wider the interval, the lower the ceiling. A `sell`
sells the `size_fraction` share of that symbol's position. Agent equity is `allocated_capital` plus the account equity change
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

`.github/workflows/cycle.yml` runs `agent.run --once --execute` at minute 7 of every hour from 15:00 to 20:00 UTC,
Monday to Friday. The cron is in UTC and fixed: the US market opens at 14:30 UTC in winter (EST) and 13:30 UTC in
summer (EDT), so 15:07 is the first slot with a completed hourly bar in winter. **When daylight saving time
starts (March), change the cron to `7 14-19 * * 1-5`.** Whether the market is open always comes from the Alpaca
clock, not from the cron. The workflow can also be started by hand (Actions > cycle > Run workflow) with two
options: `resume` (clear the halted state) and `simulate`.

**Dry run** (`simulate` ticked): one full cycle with `--ignore-market-clock` and no `--execute`, so no order can
be sent, even when the market is closed. It installs the dependencies, loads the Timestral weights (and caches
them), calls Alpaca and Mistral with the real keys, then commits `journal.db` and deploys the dashboard. The
cycle is stored as `sim-...` and is not shown on the dashboard. It costs two Mistral calls (one conversation for all symbols).

Setup, once, in the GitHub repository:

1. Settings > Secrets and variables > Actions > repository secrets: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (paper
   keys) and `MISTRAL_API_KEY`. `HF_TOKEN` is optional (faster Hugging Face downloads).
2. Settings > Pages > Build and deployment > Source: **GitHub Actions**.
3. Settings > Actions > General: Actions enabled, and workflow permissions "Read and write" (the workflow already
   asks for `contents: write`, but an organization policy can override it).

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
`(cycle, symbol, step)` (the LLM decisions of a cycle are one step). A step already stored is read back, never redone: re-running a cycle resumes where it
stopped, without a new LLM call or a duplicate order. Network calls are only retried on transient errors (network,
429, 5xx), with an increasing delay and a bounded number of attempts. An invalid LLM answer is retried once, then
rejected (no decision for any symbol of that cycle); invalid data or an invalid forecast is never retried. After a timeout on an
order, the order is looked up by its `client_order_id` before any new submission.

## How do we know the decisions are sound?

`uv run python -m agent.backtest` replays the last 180 days of real hourly bars (Alpaca, 8 ETFs,
2026-05-20 to 2026-11-13) walk-forward: at each evaluation point (every 3 bars, 1,579 points) the
forecast and the decision only see bars up to that moment. Decisions go through the same `risk.py` rules
and sizing as live, and orders are filled at the next bar close (a test checks that changing the future
never changes a decision input). Full tables: `reports/backtest.md` and `reports/backtest.json`. The LLM
outputs are cached in `reports/llm_cache.db`, so a rerun costs nothing. Use `--no-llm` or `--no-compare`
to skip parts.

**Forecast quality** (horizon: 6 hourly bars; the naive forecast is "the price stays where it is")

| Model | Points | Error vs naive (MAE ratio) | Right direction | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| Timestral-28M, all points | 1,579 | 0.998 | 50.4% | 78.3% (target 80%) | 2.28% | 0.03 |
| Timestral-28M, comparison subset | 320 | 1.009 | 50.6% | 75.6% | 2.25% | 0.03 |
| Timestral-209M, comparison subset | 320 | 1.019 | 49.4% | 75.3% | 2.27% | 0.14 |

- **The intervals are well calibrated on average, not at every date**: the 10%-90% interval contains the real
  price 78.3% of the time over the whole period, close to the 80% target. That average hides a drift (too wide
  from May to August, slightly too narrow since September, see "Known limits"). The agent uses the interval to
  size positions and to refuse uncertain buys (`max_uncertainty`), so treat it as approximately, not exactly,
  reliable.
- **The median has no edge over the naive forecast** on liquid ETFs at a 6-hour horizon
  (error ratio 1.00, direction 50%). This is expected for such markets: the agent trades on a weak signal, not on a proven edge.
- **209M is not better than 28M** on the same points (error ratio 1.019 against 1.009, direction 49.4% against 50.6%) and is
  about 3.5x slower on CPU, so the agent keeps 28M.

**Decisions against baselines** (last 28 days, 59 decision times, same rules and sizing, $10,000 allocated)

| Strategy | Return | Max drawdown | Trades | Average exposure |
| --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% |
| Equal-weight buy and hold | -1.09% | 3.18% | 8 | 88.9% |
| Momentum rule | -3.65% | 4.31% | 224 | 67.4% |
| Timestral-only rule (no LLM) | -1.80% | 5.48% | 37 | 83.6% |
| Timestral + LLM (the agent) | -1.17% | 3.77% | 55 | 54.3% |

The equal-weight buy and hold buys each of the 8 ETFs once, in equal parts of the exposure limit, and holds. The
other baselines and the agent go through the same risk rules and sizing.

**How the LLM decides.** One conversation per cycle (two Mistral calls for all the symbols). The LLM is shown the
portfolio (equity, cash, positions, return since the start and today) and calls the tool for each symbol; the tool
returns the forecast and a signal computed by the code (expected return over interval width). The prompt gives it
reference points for that signal (median 0.016, 90th percentile 0.045 of the absolute signal over the 1,138
evaluation points before the decision window, up to 2026-10-16) but no threshold or formula: it judges how strong
each forecast is, weighs the symbols against each other and against the portfolio, and gives for each symbol an
action, a confidence, a `size_fraction` (share of the maximum position for a buy, share of the current position
for a sell) and a rationale. The code turns the size into dollars or shares and applies the risk rules, including
the refusal to buy against the forecast. The Timestral-only baseline acts above a signal of 0.028 (75th percentile
of the same pre-window data).

Earlier versions were tried and are not retained as results: a prompt with a threshold of 0.02 read on all the
history (including the test window, hence biased), a prompt with no threshold that made 5 trades in 28 days, a
prompt with a hard threshold as an instruction (the LLM then applied a formula, and in a simulated cycle still
bought below it), and a version that decided each symbol in its own LLM call without seeing the portfolio.

The risk limits were raised a little on purpose (position 25%, exposure 90%, minimum confidence 0.5,
`max_uncertainty` 0.08, daily loss 10%, capital floor $5,000); they were chosen from the amount of risk wanted,
not tuned on returns.

**Result and how to read it.** Over 59 conversations (441 symbol decisions, 0 failures) the LLM chose 65 buys (mean
size 0.22, mean confidence 0.48), 63 sells (mean size 0.45) and 313 holds. None of its buys went against the
forecast, and 57 of its 128 buys and sells had a confidence below 0.5 and were blocked by the minimum; the agent
made 55 trades and was invested 54% of the time on average. -1.17% against -1.09% for the equal-weight buy and hold
and -1.80% for the Timestral-only rule is all within the noise of a 28-day window: the forecast has no measurable
edge (direction 50%), and this is not evidence of skill. The agent's drawdown (3.77%) is close to the buy and
hold's (3.18%). The claim is that the agent makes explained decisions inside risk limits, not that it beats the
market or the baselines.

## Known limits

- **The LLM's confidence is low** (mean 0.48 on its buys and 0.45 on its sells, against a minimum of 0.5), so the
  code blocks many of its decisions. The limits are applied as written; they were not loosened to make the agent
  trade more. In an earlier 5-symbol run it also bought against the forecast in 24 of 60 buys; the code blocks that.
- **What the LLM already knows.** The LLM only receives numbers (last price, forecast, interval) with no date and
  no news, but it sees the ticker, and its training data may cover part of the backtest window: the backtest
  LLM row is not proof of skill. The live paper decisions are out-of-sample by construction. Mistral publishes no cutoff
  for `mistral-small-2603` (third-party directories say June 2025, unverified), so part of the window may be inside
  its training data; symbols were not anonymised.
- **Universe.** The 8 ETFs suggested by the brief are used. Its FRED macro drivers (Brent, 10-year and 2-year
  yields, DXY, VIX, high-yield spread) are not used yet: the forecast is univariate, built from each ETF's own
  hourly closes. The LLM also sizes sells (a share of the position); the backtest had 63 sell decisions with a
  mean size of 0.45, so partial sells are exercised.
- **No transaction costs** in the backtest (fills at the next bar close, no spread, no fees). Alpaca charges no
  commission; its regulatory fees (SEC, FINRA TAF, on sells) are tiny and it is not documented whether paper
  accounts simulate them. At a few basis points per trade and about 20 trades of at most $2,500 in 28 days, costs are
  below 0.02% of the capital (estimate, not simulated).
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
- **The 80% range calibration drifts over time.** The 10%-90% interval was too wide from May to August (about
  17% of points outside it, 20% expected) and slightly too narrow since September (about 24% outside). The 78.3% overall coverage above averages both periods, so the interval used to
  size positions and refuse uncertain buys is not equally reliable at every date.
- Baseline parameters (`rule_signal_threshold`, `momentum_bars`) are fixed in `config.toml`; the threshold comes
  from the data before the decision window, `momentum_bars` is not tuned.
- **No news.** The bonus (news as covariates for Timestral) was tried (Alpaca article counts and LLM sentiment),
  showed no measurable improvement, and was removed from the code; it is still in the git history.

## Development

`uv run ruff check .`, `uv run mypy .`, `uv run pytest`, and `cd web && pnpm build`.
