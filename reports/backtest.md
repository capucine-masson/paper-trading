Symbols: SPY, QQQ, AAPL, MSFT, GLD. Horizon: 6 hourly bars. History 2026-05-19 to 2026-11-13, one evaluation point every 3 bars.

### Forecast quality

| Model | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage | Mean width | Seconds per forecast |
| --- | --- | --- | --- | --- | --- | --- |
| Main model, all points | 1093 | 1.000 | 50.1% (n=1092) | 78.7% | 2.82% | 0.04 |
| Main model, comparison subset | 200 | 1.003 | 54.0% (n=200) | 81.0% | 2.77% | 0.04 |
| Larger model, comparison subset | 200 | 1.002 | 51.0% (n=200) | 78.5% | 2.72% | 0.14 |

### Decisions against baselines

Window starts 2026-10-16, 59 decision times, 0 LLM failures (treated as hold).

| Strategy | Return | Max drawdown | Trades | Average exposure | Final equity |
| --- | --- | --- | --- | --- | --- |
| Cash (never trade) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
| Buy and hold | -1.01% | 3.28% | 26 | 80.4% | $9,898.57 |
| Momentum rule | -1.58% | 2.40% | 138 | 35.9% | $9,842.50 |
| Timestral-only rule | +0.13% | 2.14% | 17 | 33.2% | $10,013.41 |
| Timestral + LLM (the agent) | +0.00% | 0.00% | 0 | 0.0% | $10,000.00 |
