Symbols: SPY, QQQ, XLE, XLF, XLU, TLT, GLD, EEM. Horizon: 6 hourly bars. History 2026-05-21 to 2026-11-17, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| mistralai/Timestral-28M | 436 | 0.999 | 51.2% (n=434) | 72.5% | 2.57% | 0.18 |
| mistralai/Timestral-209M | 436 | 1.010 | 50.2% (n=434) | 76.8% | 2.70% | 1.51 |

### Decisions against baselines

Window starts 2026-10-16, 65 decision times, 0 LLM failures (no order at that time).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Equal-weight buy and hold | -2.44% | 2.82% | 8 | 78.3% | $9,756.31 |
| Timestral-only rule | -2.90% | 4.90% | 33 | 66.6% | $9,709.83 |
| Buy and hold (same exposure as agent) | -1.94% | 2.24% | 8 | 62.3% | $9,806.15 |
| Timestral + LLM (the agent) | -1.79% | 3.52% | 78 | 63.6% | $9,821.16 |
