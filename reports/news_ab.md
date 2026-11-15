Symbols: SPY, QQQ, AAPL, MSFT, GLD. Horizon: 6 hourly bars. Price history 2026-05-19 to 2026-11-13. Low-volume symbols: GLD.

### Article count

Number of articles over the last 6 bars (past-only covariate). Symbols: AAPL, GLD, MSFT, QQQ, SPY.

| Variant | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage |
| --- | --- | --- | --- | --- |
| Without news | 1093 | 1.000 | 50.1% (n=1092) | 78.7% |
| Article count | 1093 | 1.001 | 49.5% (n=1092) | 78.6% |

Paired change of the absolute error: +0.0058 USD (+0.12%), 95% interval [-0.0128, +0.0244], news better on 51% of 1093 points. **No measurable difference (interval includes zero).**

| Symbol | Articles per week | MAE ratio without | MAE ratio with | Verdict |
| --- | --- | --- | --- | --- |
| AAPL | 77 | 1.004 | 1.006 | No measurable difference (interval includes zero). |
| GLD | 9 (low volume) | 1.011 | 1.015 | No measurable difference (interval includes zero). |
| MSFT | 99 | 1.005 | 1.005 | No measurable difference (interval includes zero). |
| QQQ | 40 | 0.997 | 0.999 | No measurable difference (interval includes zero). |
| SPY | 176 | 0.984 | 0.982 | No measurable difference (interval includes zero). |

### LLM sentiment

Relevance-weighted mean sentiment over the last 6 bars, NaN with no news (past-only covariate). Symbols: AAPL, MSFT, QQQ, SPY.

| Variant | Points | MAE ratio vs naive | Direction hit rate | 10%-90% coverage |
| --- | --- | --- | --- | --- |
| Without news | 890 | 0.998 | 51.6% (n=889) | 78.7% |
| LLM sentiment | 890 | 1.000 | 49.7% (n=889) | 78.1% |

Paired change of the absolute error: +0.0077 USD (+0.16%), 95% interval [-0.0115, +0.0268], news better on 51% of 890 points. **No measurable difference (interval includes zero).**

| Symbol | Articles per week | MAE ratio without | MAE ratio with | Verdict |
| --- | --- | --- | --- | --- |
| AAPL | 77 | 1.004 | 1.003 | No measurable difference (interval includes zero). |
| MSFT | 99 | 1.005 | 1.005 | No measurable difference (interval includes zero). |
| QQQ | 40 | 0.997 | 1.002 | No measurable difference (interval includes zero). |
| SPY | 176 | 0.984 | 0.983 | No measurable difference (interval includes zero). |

### LLM scoring cost

690 calls, 644,763 input and 240,329 output tokens, $0.24. 9408 articles scored, 13 left unscored (1 failed batches).

Limits: points are spaced by the stride and overlap in time, so the intervals are optimistic; one market regime; a single Timestral run per variant.
