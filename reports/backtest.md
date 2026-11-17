Symbols: SPY, QQQ, XLE, XLF, XLU, TLT, GLD, EEM. Horizon: 6 hourly bars. History 2026-05-21 to 2026-11-16, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| mistralai/Timestral-28M | 426 | 0.991 | 52.4% (n=424) | 72.8% | 2.56% | 0.34 |

### Decisions against baselines

Window starts 2026-10-16, 63 decision times, 1 LLM failures (no order at that time).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Equal-weight buy and hold | -2.04% | 2.82% | 8 | 78.3% | $9,796.23 |
| Timestral-only rule | -2.22% | 4.90% | 31 | 66.2% | $9,778.42 |
| Buy and hold (same exposure as agent) | -1.69% | 2.33% | 8 | 64.8% | $9,831.36 |
| Timestral + LLM (the agent) | -2.52% | 5.31% | 49 | 66.2% | $9,748.18 |
