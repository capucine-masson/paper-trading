Symbols: SPY, QQQ, AAPL, MSFT, GLD. Horizon: 6 hourly bars. History 2026-05-20 to 2026-11-13, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| Main model, all points | 1080 | 1.000 | 50.0% (n=1079) | 78.5% | 2.82% | 0.03 |
| Main model, comparison subset | 200 | 1.005 | 45.5% (n=200) | 79.0% | 2.80% | 0.03 |
| Larger model, comparison subset | 200 | 1.014 | 45.5% (n=200) | 77.5% | 2.73% | 0.14 |

### Decisions against baselines

Window starts 2026-10-16, 59 decision times, 0 LLM failures (no order at that time).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
| Buy and hold | -1.73% | 3.69% | 19 | 90.7% | $9,826.69 |
| Momentum rule | -1.93% | 3.19% | 188 | 46.4% | $9,806.95 |
| Timestral-only rule | +1.24% | 3.06% | 36 | 70.8% | $10,123.93 |
| Timestral + LLM (the agent) | -0.95% | 1.85% | 17 | 34.6% | $9,904.78 |
