# News analysis: hypotheses and protocol (written before any result)

Written 2026-11-14, before running `agent/news_analysis.py`. Analysis only: no new LLM call (articles and
LLM scores come from `reports/news_cache.db`), no change to the agent, nothing committed.

## Data
The same 1,093 walk-forward points as the A/B (5 symbols, 6-bar horizon, Timestral-28M, May to Nov 2026).
Target of a point: the absolute log move `|log(price after 6 bars / last price)|`.
Past realized volatility: standard deviation of hourly log returns over the 24 bars before the point
(missing bars ignored). Sentiment features exist for SPY, QQQ, AAPL and MSFT only (GLD is not scored);
a window without scored news gives a feature value of 0.

## Split
- Tuning period: points before 2026-08-30. Confirmation period: points from 2026-09-01.
- The two days in between are dropped (embargo) so that no 6-bar target straddles both periods.
- Every threshold, window or variant is chosen on the tuning period only, with one rule fixed below.
  Only the chosen variant is evaluated on the confirmation period, without any change.
- Features are standardized per symbol with the mean and standard deviation of the tuning period.

## Hypotheses
**H1.** High news volume (or high absolute sentiment) precedes larger absolute moves over the next 6 bars,
beyond what past realized volatility explains.
- Variants tried on tuning: log(1 + article count) and absolute relevance-weighted sentiment, each over
  6, 12 and 24 bars (6 variants).
- Selection: the variant with the largest positive t-statistic of the news coefficient in
  `|move| ~ volatility + news` on the tuning period.
- Test on confirmation: (a) the news coefficient (pooled, symbol-standardized, and per symbol);
  (b) out-of-sample squared-error improvement of `volatility + news` over `volatility only`, both fitted on the
  tuning period and not refitted.

**H2.** The 10%-90% range is too narrow when news volume is high.
- "High" means article count over 6 bars strictly above the tuning-period median of that symbol; "low" is the rest.
- Variants tried on tuning: windows of 6, 12 and 24 bars; the chosen one is the window with the largest
  (high minus low) share of points outside the range on the tuning period.
- Test on confirmation: the difference in the share of points outside the range, high minus low, pooled and per
  symbol. Expected under H2: positive.

**H3.** A finer covariate helps Timestral.
- Variants tried (each run through Timestral as a past-only covariate): article count over 12 bars, article
  count over 24 bars, count surprise over 6 bars (count minus the mean of the same count over the previous
  35 bars, i.e. about 5 sessions), absolute sentiment over 6, 12 and 24 bars (6 variants).
- Selection: the variant with the lowest mean absolute error of the median on the tuning period.
- Test on confirmation: the paired change of the absolute error against the covariate-free forecast, pooled
  and per symbol. Expected under H3: negative.

## Uncertainty and decision rule
- Confidence intervals: bootstrap by calendar day (days are resampled, all symbols of a day kept together),
  5,000 resamples, because consecutive points overlap in time. They are still optimistic: one market regime and
  few independent days.
- Three hypotheses are tested, so an effect is called **clear** only if, on the confirmation period, the pooled
  98.3% interval (95% corrected for 3 hypotheses) excludes zero in the direction predicted, and the sign is the
  predicted one for at least 3 of the 5 symbols. Otherwise the answer is "no clear effect" and the analysis stops.
- Every variant tried is reported with its tuning-period result, including failures. Confirmation results are
  only given for the variant selected on tuning.
