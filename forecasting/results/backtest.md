# Walk-forward backtest (sliding window)

Each origin: `forecast()` sees only the rows before it, trimmed to the window, and is scored on
what came next. Baseline columns are "same time yesterday" on the same origins (they need a
day of history, so they can cover fewer origins). Reproduce with the command in
`forecasting/backtest.py`.

| dataset | window | origins | horizon | MAPE % mean (median) | where baseline exists: forecast vs baseline | models used |
|---|---|---|---|---|---|---|
| aws-nov7 | 72 h | 34 | 1h | 4.41 (3.69) | n/a | arima-short 34 |
| aws-nov7 | 72 h | 34 | 6h | 11.42 (8.14) | n/a | arima-short 34 |
| azure | 24 h | 168 | 1h | 0.92 (0.78) | 0.92 vs 1.01 (n=168) | arima-short 168 |
| azure | 24 h | 168 | 6h | 1.06 (0.93) | 1.06 vs 1.00 (n=163) | arima-short 168 |
| azure | 24 h | 168 | 24h | 1.19 (1.16) | 1.19 vs 1.01 (n=145) | arima-short 168 |
| azure | 48 h | 168 | 1h | 0.91 (0.79) | 0.91 vs 1.01 (n=168) | arima-short 168 |
| azure | 48 h | 168 | 6h | 1.07 (0.98) | 1.07 vs 1.00 (n=163) | arima-short 168 |
| azure | 48 h | 168 | 24h | 1.16 (1.12) | 1.16 vs 1.01 (n=145) | arima-short 168 |
| azure | 72 h | 168 | 1h | 0.95 (0.84) | 0.95 vs 1.01 (n=168) | arima 168 |
| azure | 72 h | 168 | 6h | 1.06 (0.92) | 1.06 vs 1.00 (n=163) | arima 168 |
| azure | 72 h | 168 | 24h | 1.17 (1.03) | 1.17 vs 1.01 (n=145) | arima 168 |
| azure | 168 h | 168 | 1h | 0.85 (0.80) | 0.85 vs 1.01 (n=168) | arima 166, naive 2 |
| azure | 168 h | 168 | 6h | 0.92 (0.83) | 0.92 vs 1.00 (n=163) | arima 166, naive 2 |
| azure | 168 h | 168 | 24h | 1.05 (1.00) | 1.05 vs 1.01 (n=145) | arima 166, naive 2 |
| wikipedia | 24 h | 168 | 1h | 1.30 (1.02) | 1.30 vs 3.07 (n=168) | arima-short 168 |
| wikipedia | 24 h | 168 | 6h | 8.29 (6.67) | 8.29 vs 3.00 (n=163) | arima-short 168 |
| wikipedia | 24 h | 168 | 24h | 13.69 (13.81) | 13.69 vs 2.99 (n=145) | arima-short 168 |
| wikipedia | 48 h | 168 | 1h | 1.27 (0.99) | 1.27 vs 3.07 (n=168) | arima-short 168 |
| wikipedia | 48 h | 168 | 6h | 7.91 (6.21) | 7.91 vs 3.00 (n=163) | arima-short 168 |
| wikipedia | 48 h | 168 | 24h | 13.16 (13.46) | 13.16 vs 2.99 (n=145) | arima-short 168 |
| wikipedia | 72 h | 168 | 1h | 0.91 (0.67) | 0.91 vs 3.07 (n=168) | arima 168 |
| wikipedia | 72 h | 168 | 6h | 2.94 (2.70) | 2.94 vs 3.00 (n=163) | arima 168 |
| wikipedia | 72 h | 168 | 24h | 3.71 (3.34) | 3.71 vs 2.99 (n=145) | arima 168 |
| wikipedia | 168 h | 168 | 1h | 1.00 (0.72) | 1.00 vs 3.07 (n=168) | arima 168 |
| wikipedia | 168 h | 168 | 6h | 3.99 (3.30) | 3.99 vs 3.00 (n=163) | arima 168 |
| wikipedia | 168 h | 168 | 24h | 4.71 (3.85) | 4.71 vs 2.99 (n=145) | arima 168 |
