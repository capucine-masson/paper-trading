Symbols: SPY, QQQ, XLE, XLF, XLU, TLT, GLD, EEM. Horizon: 6 hourly bars. History 2026-05-20 to 2026-11-13, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| Timestral-28M | 1579 | 0.998 | 51.0% (n=1574) | 79.4% | 2.40% | 0.19 |

### Decisions against baselines

Window starts 2026-10-16, 59 decision times, 0 LLM failures (no order at that time).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
| Equal-weight buy and hold | -1.13% | 3.18% | 8 | 88.9% | $9,886.67 |
| Momentum rule | -4.29% | 4.50% | 226 | 68.2% | $9,570.59 |
| Timestral-only rule | -0.78% | 4.26% | 34 | 79.7% | $9,922.39 |
| Timestral + LLM (the agent) | -0.23% | 4.85% | 58 | 81.7% | $9,976.70 |
