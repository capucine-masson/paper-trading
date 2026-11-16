Symbols: SPY, QQQ, XLE, XLF, XLU, TLT, GLD, EEM. Horizon: 6 hourly bars. History 2026-05-20 to 2026-11-13, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| Main model, all points | 1579 | 0.998 | 50.4% (n=1574) | 78.3% | 2.28% | 0.03 |
| Main model, comparison subset | 320 | 1.009 | 50.6% (n=316) | 75.6% | 2.25% | 0.03 |
| Larger model, comparison subset | 320 | 1.019 | 49.4% (n=316) | 75.3% | 2.27% | 0.23 |

### Decisions against baselines

Window starts 2026-10-16, 59 decision times, 0 LLM failures (no order at that time).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
| Equal-weight buy and hold | -1.09% | 3.18% | 8 | 88.9% | $9,891.17 |
| Momentum rule | -3.65% | 4.31% | 224 | 67.4% | $9,634.84 |
| Timestral-only rule | -1.80% | 5.48% | 37 | 83.6% | $9,820.07 |
| Timestral + LLM (the agent) | -1.17% | 3.77% | 55 | 54.3% | $9,882.57 |
