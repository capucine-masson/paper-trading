# Getting started

Paper trading only: no real money is ever used. **Part 1** runs the agent on your machine. **Part 2**
(optional) makes it run by itself every hour on GitHub.

## Part 1: Run locally

**Prerequisites**

- [Git](https://git-scm.com/downloads)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (installs Python 3.12 for you)
- [Node 22](https://nodejs.org) and [pnpm](https://pnpm.io/installation) (dashboard only)
- Three free accounts, each giving keys:
  - [Alpaca paper trading](https://app.alpaca.markets/signup): `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`
    (paper keys, on the [paper dashboard](https://app.alpaca.markets/paper/dashboard/overview))
  - [Mistral AI Studio](https://console.mistral.ai/api-keys): `MISTRAL_API_KEY`
  - [FRED](https://fredaccount.stlouisfed.org/apikeys): `FRED_API_KEY`

**1. Get the code and install**

```bash
git clone https://github.com/capucine-masson/paper-trading.git
cd paper-trading
uv sync --frozen
```

The first forecast downloads the Timestral weights (about 111 MB) from Hugging Face.

**2. Add your keys**

```bash
cp .env.example .env        # PowerShell: copy .env.example .env
```

Fill `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `MISTRAL_API_KEY` and `FRED_API_KEY` in `.env`. `HF_TOKEN` is
optional (a [Hugging Face token](https://huggingface.co/settings/tokens) only speeds up the download).

**3. Start with an empty journal**

The repository ships the author's `journal.db`, including the starting equity used for the loss limits.
Delete it so the agent starts from your own Alpaca account (it is recreated on the first run):

```bash
rm journal.db               # PowerShell: Remove-Item journal.db
```

**4. Run one cycle**

```bash
uv run python -m agent.run --ignore-market-clock    # simulation: no order, works when the market is closed
uv run python -m agent.run --execute                # real paper orders, only when the US market is open
```

Each symbol prints its forecast, the LLM decision, the risk verdict and the order. Everything is stored in
`journal.db`. Settings are in `config.toml`.

**5. See the dashboard**

```bash
uv run python -m agent.export                       # journal.db -> web/public/data/
cd web
pnpm install
pnpm dev                                            # http://localhost:3030
```

**6. Check the code and reproduce the backtest**

```bash
uv run ruff check . && uv run mypy . && uv run pytest
uv run python -m agent.backtest                     # writes reports/backtest.md (calls Mistral)
uv run python -m agent.backtest --no-llm            # forecast quality only, no Mistral call
```

## Part 2: Deploy on GitHub Actions (optional)

The workflow `.github/workflows/cycle.yml` runs one cycle per hour of the US session, Monday to Friday.
Do the steps in order, in your own copy of the repository.

### A. Workflow setup

1. [Fork the repository](https://github.com/capucine-masson/paper-trading/fork), then open the **Actions** tab of
   your fork and enable workflows.
2. Add the secrets `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `MISTRAL_API_KEY`, `FRED_API_KEY` (and optionally
   `HF_TOKEN`) at `https://github.com/<owner>/<repo>/settings/secrets/actions`.
3. Set the Pages source to **GitHub Actions** at `https://github.com/<owner>/<repo>/settings/pages`, and the
   workflow permissions to **Read and write** at `https://github.com/<owner>/<repo>/settings/actions`.
4. Start from an empty journal: in your fork, delete the author's journal and push.

   ```bash
   git rm journal.db
   git commit -m "Reset journal"
   git push
   ```

5. Open `https://github.com/<owner>/<repo>/actions/workflows/cycle.yml`, click **Run workflow** with
   `simulate` ticked. It runs a full cycle without any order.

### B. Hourly trigger (token + cron-job.org)

GitHub often delays or skips scheduled runs, so a free external cron calls the workflow every hour. The
built-in `schedule` stays as a fallback. A duplicate run is harmless: it places no second order.

**B1. Create a GitHub token** ([new fine-grained token](https://github.com/settings/personal-access-tokens/new))

1. Name: `cron-job-dispatch`. Expiration: 90 days (note the date, you must renew it).
2. Repository access: **Only select repositories**, then your fork.
3. Repository permissions: **Actions: Read and write**. Everything else stays "No access".
4. Generate and copy the token (`github_pat_...`) now: it is shown once. Paste it only into cron-job.org,
   never in the repository, in `.env` or in a chat.

**B2. Create the cron job** ([sign up](https://cron-job.org/en/signup/), then
[console](https://console.cron-job.org) > Create cronjob)

1. Common tab:
   - Title: `trading-agent cycle`
   - URL: `https://api.github.com/repos/<owner>/<repo>/actions/workflows/cycle.yml/dispatches`
   - Schedule: **Personalized**, crontab `7 10-15 * * 1-5`, time zone `America/New_York` (follows daylight
     saving time by itself). "Next executions" must only show `:07` slots.
2. Advanced tab:
   - Request method: **POST**
   - Request body: `{"ref":"main"}`
   - Headers (button **Add**, one per line):

     | Name | Value |
     |---|---|
     | `Authorization` | `Bearer ` followed by the token (one space, no quotes) |
     | `Accept` | `application/vnd.github+json` |
     | `X-GitHub-Api-Version` | `2022-11-28` |
     | `Content-Type` | `application/json` |

3. Notifications tab: enable the alert on failure, so an expired token does not go unnoticed.
4. Save, then **Test run**. Expected: **204 No Content** and a new `cycle` run in the Actions tab. A test run
   is a real cycle: it places paper orders if the market is open.

Errors: **401** token mistyped or expired; **403** token lacks Actions read and write; **404** wrong method
(must be POST), missing `Authorization` header, token cannot see the repository or typo in the URL; **422**
wrong body or `Content-Type`.

Renew the token before it expires: [your tokens](https://github.com/settings/personal-access-tokens) > the
token > Regenerate, then paste the new value in the `Authorization` header.

### C. Resume a failed cycle

A failed cycle is resumed with the same cycle id: journaled steps (LLM output, orders) are read back, never
repeated. On GitHub, run the workflow with `cycle_id` (the cycle to resume, e.g. `20261116T15`) and `resume`
ticked. Locally:

```bash
uv run python -m agent.run --execute --cycle-id <id> --resume
```
