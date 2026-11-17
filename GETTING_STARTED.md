# Getting started

Everything needed to run the agent from a fresh clone. Paper trading only: no real money is ever used.

## What you need

- **Python 3.12** (`uv` installs it for you if missing) and [`uv`](https://docs.astral.sh/uv/)
- [**Node 22**](https://nodejs.org) and [`pnpm`](https://pnpm.io/installation) (only to view the dashboard locally)
- Three free accounts, each giving a key:
  - [**Alpaca paper trading**](https://app.alpaca.markets/signup): `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`
    (paper keys, shown on the [paper dashboard](https://app.alpaca.markets/paper/dashboard/overview))
  - [**Mistral AI Studio**](https://console.mistral.ai/api-keys): `MISTRAL_API_KEY`
  - [**FRED**](https://fredaccount.stlouisfed.org/apikeys) (create an account, then request an API key):
    `FRED_API_KEY`

## 1. Install

```bash
uv sync --frozen
```

This installs Timestral and the CPU build of `torch`. The first forecast downloads the Timestral weights
(about 111 MB) from Hugging Face.

## 2. Add the keys

```bash
cp .env.example .env        # PowerShell: copy .env.example .env
```

Fill the four required keys in `.env` (the file is git-ignored): `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`,
`MISTRAL_API_KEY` and `FRED_API_KEY`. `HF_TOKEN` is optional (a
[Hugging Face token](https://huggingface.co/settings/tokens) only speeds up the weights download).

## 3. Run one cycle

```bash
# Simulation: full pipeline, no order is sent (works even when the market is closed)
uv run python -m agent.run --ignore-market-clock

# Real paper orders (only when the US market is open)
uv run python -m agent.run --execute
```

The console prints, for each symbol, the Timestral forecast, the LLM decision and rationale, the risk verdict
and the order. Every step is stored in `journal.db` (committed on purpose: it is the agent's memory between
runs, including on GitHub Actions). Simulated cycles are marked `sim-` and never appear on the
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

The agent runs on its own through `.github/workflows/cycle.yml`, once per hour of the US session, Monday to
Friday. Do the steps below in order, in your own copy of the repository.

### A. Set up the workflow

1. Push the repository to GitHub.
2. Add the secrets `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `MISTRAL_API_KEY` and `FRED_API_KEY` (and optionally `HF_TOKEN`) in
   Settings > Secrets and variables > Actions
   (`https://github.com/<owner>/<repo>/settings/secrets/actions`).
3. Pages source: **GitHub Actions** (`https://github.com/<owner>/<repo>/settings/pages`). Workflow permissions:
   "Read and write" (`https://github.com/<owner>/<repo>/settings/actions`).
4. Open `https://github.com/<owner>/<repo>/actions/workflows/cycle.yml` > Run workflow, with `simulate` ticked,
   to check everything works without any order.

### B. Choose what triggers the hourly run

The workflow has a built-in GitHub `schedule` (`7 15-20 * * 1-5`, UTC, winter time; in summer change it to
`7 14-19 * * 1-5`). You can test it, but **GitHub often delays or silently skips scheduled runs**, especially
on a recent repository. Keep it only as a fallback and use an **external cron** as the main trigger: a free
service that calls the GitHub API every hour. A duplicate run is harmless, it reads the journal back and places
no second order. The steps below use [cron-job.org](https://cron-job.org) (free account, no card).

**B1. Create a GitHub token** ([new fine-grained token](https://github.com/settings/personal-access-tokens/new))

1. Token name: `cron-job-dispatch`. Expiration: 90 days (write the date down, you must renew it).
2. Resource owner: your account. Repository access: **Only select repositories**, then pick this repository.
3. Repository permissions: **Actions: Read and write**. Leave everything else at "No access".
4. Generate the token and copy it now (`github_pat_...`): GitHub shows it only once. Paste it only into
   cron-job.org. Never put it in the repository, in `.env` or in a chat.

**B2. Create the cron job** ([sign up](https://cron-job.org/en/signup/), then [console](https://console.cron-job.org) > Create cronjob)

1. Common tab:
   - Title: `trading-agent cycle`.
   - URL: `https://api.github.com/repos/<owner>/<repo>/actions/workflows/cycle.yml/dispatches`
   - Schedule: **Personalized**, crontab expression `7 10-15 * * 1-5`, job time zone `America/New_York`.
     This is minute 7 of hours 10 to 15, Monday to Friday, New York time: it follows daylight saving time by
     itself. Check "Next executions" on the right: only `:07` slots should appear.
   - Keep "Save responses in job history" on.
2. Advanced tab:
   - Request method: **POST**.
   - Request body: `{"ref":"main"}`
   - Headers (button **Add**, once per line):

     | Name | Value |
     |---|---|
     | `Authorization` | `Bearer ` then the token (one space, no quotes, nothing after it) |
     | `Accept` | `application/vnd.github+json` |
     | `X-GitHub-Api-Version` | `2022-11-28` |
     | `Content-Type` | `application/json` |

   - Leave "Requires HTTP authentication" off.
3. Notifications tab: enable the alert on failure, so an expired token does not go unnoticed.
4. Save, then run **Test run**. Expected status: **204 No Content**, and a new `cycle` run appears in the
   Actions tab of the repository. A test run is a real cycle: it places paper orders if the market is open.

| Status | Meaning |
|---|---|
| 401 | Token mistyped or expired |
| 403 | Token lacks **Actions: Read and write** |
| 404 | Method is not POST, the `Authorization` header is missing, the token cannot see the repository, or the URL has a typo |
| 422 | Body or `Content-Type` header is wrong |

Renew the token before its expiration date ([your tokens](https://github.com/settings/personal-access-tokens) >
the token > Regenerate token, then paste the new value in the `Authorization` header).

Market open or closed is always decided by the Alpaca clock in code, never by the trigger.

### C. Resume a failed cycle

A failed cycle is resumed in place with the same cycle id: journaled steps (LLM output, orders) are read back,
never repeated. To resume by hand, use the workflow inputs `cycle_id` (the cycle to resume) and `resume`
(clears the halted state), or locally `uv run python -m agent.run --execute --cycle-id <id> --resume`.

Settings (symbols, horizon, risk limits) live in `config.toml`. The emergency stop is `enabled = false` there.
