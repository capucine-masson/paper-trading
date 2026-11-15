# News analysis results

Protocol and hypotheses: `reports/news_analysis_plan.md` (written before this run). 1093 points: 348 in the tuning period (before 2026-08-30), 735 in the confirmation period (from 2026-09-01). Points overlap in time; intervals are day-bootstrap intervals and still optimistic.

## H1: news and the size of the next move

Tuning period, every variant (t-statistic of the news coefficient, controlling for volatility):

| Variant | Symbols | Points | News coefficient | t-statistic |
| --- | --- | --- | --- | --- |
| count_6 | 5 | 348 | -0.034 | -0.61 |
| count_12 | 5 | 348 | -0.045 | -0.80 |
| count_24 | 5 | 348 | -0.023 | -0.40 |
| abs_sentiment_6 | 4 | 286 | -0.038 | -0.67 |
| abs_sentiment_12 | 4 | 286 | -0.056 | -0.97 |
| abs_sentiment_24 | 4 | 286 | +0.090 | +1.57 |

Selected on tuning: **abs_sentiment_24**.

Confirmation (596 points), 98.3% day-bootstrap intervals:

- News coefficient, controlling for volatility (standardized units): -0.0424 [-0.1716, +0.0603]
- Out-of-sample squared-error gain of volatility + news over volatility only (fitted on tuning, standardized units): -0.0246 [-0.0538, -0.0027]

| Symbol | Points | News coefficient |
| --- | --- | --- |
| AAPL | 147 | +0.0139 [-0.1881, +0.2166] |
| MSFT | 142 | +0.0648 [-0.0398, +0.1955] |
| QQQ | 153 | -0.1584 [-0.5441, +0.1244] |
| SPY | 154 | -0.0094 [-0.2664, +0.3403] |

**H1 verdict: no clear effect** (2 symbols with a positive coefficient).

## H2: the 10%-90% range is too narrow when news volume is high

Tuning period, every window (share outside the range, high minus low news):

| Window (bars) | Outside, high news | Outside, low news | Difference |
| --- | --- | --- | --- |
| 6 | 12.9% | 15.9% | -3.0% |
| 12 | 13.4% | 15.8% | -2.3% |
| 24 | 15.6% | 13.8% | +1.8% |

Selected on tuning: **24 bars** (threshold: tuning median per symbol).

Confirmation (735 points): outside the range 25.9% with high news (n=451) against 21.8% with low news (n=284); nominal 20%.
- Difference high minus low, 98.3% day-bootstrap interval: +0.0411 [-0.0547, +0.1396]

| Symbol | High n | Low n | Outside, high | Outside, low | Difference |
| --- | --- | --- | --- | --- | --- |
| AAPL | 93 | 54 | 21.5% | 22.2% | -0.7% |
| GLD | 16 | 123 | 18.8% | 22.0% | -3.2% |
| MSFT | 88 | 54 | 27.3% | 14.8% | +12.5% |
| QQQ | 116 | 37 | 25.9% | 32.4% | -6.6% |
| SPY | 138 | 16 | 29.0% | 18.8% | +10.2% |

**H2 verdict: no clear effect** (2 symbols with more misses in high-news points).

## H3: finer covariates through Timestral

Tuning period, every variant (paired change of the absolute error vs no covariate; negative is better):

| Variant | Tuning points | Relative change |
| --- | --- | --- |
| count_12 | 348 | +0.15% |
| count_24 | 348 | +0.18% |
| surprise_6 | 348 | +0.47% |
| abs_sentiment_6 | 286 | +0.10% |
| abs_sentiment_12 | 286 | +0.18% |
| abs_sentiment_24 | 286 | -0.00% |

Selected on tuning: **abs_sentiment_24**.

Confirmation (596 points), paired change of the absolute error in USD, 98.3% day-bootstrap interval: -0.0006 [-0.0388, +0.0385] (-0.01% of the baseline error)

| Symbol | Points | Change of the absolute error (USD) |
| --- | --- | --- |
| AAPL | 147 | +0.0082 [-0.0376, +0.0615] |
| MSFT | 142 | +0.0097 [-0.0765, +0.1207] |
| QQQ | 153 | -0.0031 [-0.0865, +0.0845] |
| SPY | 154 | -0.0161 [-0.0613, +0.0271] |

**H3 verdict: no clear effect** (2 symbols with a lower error).

