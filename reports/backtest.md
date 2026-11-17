Symbols: SPY, QQQ, XLE, XLF, XLU, TLT, GLD, EEM. Horizon: 6 hourly bars. History 2026-05-21 to 2026-11-16, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| mistralai/Timestral-28M | 465 | 0.992 | 53.0% (n=464) | 74.0% | 2.56% | 0.24 |

### Decisions against baselines

Window starts 2026-10-16, 63 decision times, 0 LLM failures (no order at that time).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
| Equal-weight buy and hold | -1.97% | 2.82% | 8 | 78.7% | $9,802.62 |
| Buy and hold (same exposure as agent) | -1.75% | 2.50% | 8 | 69.7% | $9,825.22 |
| Momentum rule | -6.05% | 6.19% | 239 | 66.9% | $9,395.45 |
| Timestral-only rule | -0.55% | 4.13% | 31 | 70.3% | $9,944.62 |
| Timestral + LLM (the agent) | -1.22% | 3.95% | 33 | 70.8% | $9,877.76 |
