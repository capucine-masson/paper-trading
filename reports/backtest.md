Symbols: SPY, QQQ, AAPL, MSFT, GLD. Horizon: 6 hourly bars. History 2026-05-18 to 2026-11-13, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| Main model, all points | 1108 | 1.001 | 50.0% (n=1107) | 78.8% | 2.83% | 0.07 |
| Main model, comparison subset | 200 | 0.992 | 49.0% (n=200) | 81.0% | 2.79% | 0.07 |
| Larger model, comparison subset | 200 | 1.004 | 45.5% (n=200) | 78.0% | 2.73% | 0.22 |

### Decisions against baselines

Window starts 2026-10-16, 59 decision times, 0 LLM failures (treated as hold).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
| Buy and hold | -1.01% | 3.28% | 26 | 80.4% | $9,898.57 |
| Momentum rule | -1.58% | 2.40% | 138 | 35.9% | $9,842.50 |
| Timestral-only rule | +0.13% | 2.14% | 17 | 33.2% | $10,013.41 |
| Timestral + LLM (the agent) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
