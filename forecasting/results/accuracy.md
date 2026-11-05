# Forecast accuracy (held-out last day, 15-min steps)

Reproduce: `python -m forecasting.loaders wikipedia` (rows for real traces need their
csv in data/, which is gitignored), then `python -m forecasting.evaluate`.

Known limitation: the spike pattern's spikes land at random times, so no model can
predict them; ARIMA only widens its uncertainty band there.

| dataset | model | MAE (req/min) | RMSE | MAPE % |
|---|---|---|---|---|
| synthetic-steady | arima | 5.3 | 6.4 | 1.06 |
| synthetic-steady | same-time-yesterday | 7.5 | 9.0 | 1.50 |
| synthetic-cycle | arima | 5.4 | 7.0 | 1.09 |
| synthetic-cycle | same-time-yesterday | 7.4 | 9.4 | 1.50 |
| synthetic-spike | arima | 177.6 | 624.5 | 19.37 |
| synthetic-spike | same-time-yesterday | 193.1 | 858.1 | 22.26 |
| synthetic-growth | arima | 9.9 | 12.1 | 1.05 |
| synthetic-growth | same-time-yesterday | 100.4 | 101.7 | 10.56 |
| wikipedia | arima | 22.7 | 28.0 | 3.28 |
| wikipedia | same-time-yesterday | 32.1 | 32.7 | 4.68 |
| azure | arima | 9.2 | 10.9 | 1.32 |
| azure | same-time-yesterday | 5.9 | 7.3 | 0.85 |
| wikipedia | lstm (Colab run) | 28.6 | 31.4 | 4.10 |

## Real AWS runs (each ~1 h: too short for a held-out day, small-sample check only)

Data: `aws s3 sync s3://<bucket>/metrics/ <dir>`, then `python -m forecasting.loaders aws-run <dir>`. Phase windows: data/*-notes.md.

### aws-run-2026-11-04.csv

Unbroken stretch 2026-11-04T13:23:00Z .. 2026-11-04T13:37:00Z (15 min). `forecast()` on the first 10 min gives model `naive`, level 2138 req/min. Against the last 5 min (actual 2072-2278): MAE 49.6, MAPE 2.26%.

Whole run (20 rows, gaps included) gives model `naive`, 24 h peak 1837 req/min (observed per-minute max 2390).

### aws-run-2026-11-05-patterns.csv

Unbroken stretch 2026-11-05T10:14:00Z .. 2026-11-05T11:14:00Z (61 min). `forecast()` on the first 46 min gives model `naive`, level 255 req/min. Against the last 15 min (actual 106-542): MAE 134.1, MAPE 62.61%.

Whole run (198 rows, gaps included) gives model `naive`, 24 h peak 268 req/min (observed per-minute max 542).

### aws-run-2026-11-05.csv

Unbroken stretch 2026-11-05T07:43:00Z .. 2026-11-05T08:46:00Z (64 min). `forecast()` on the first 49 min gives model `naive`, level 328 req/min. Against the last 15 min (actual 311-334): MAE 3.4, MAPE 1.05%.

Whole run (243 rows, gaps included) gives model `naive`, 24 h peak 144 req/min (observed per-minute max 2293).
