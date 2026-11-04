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
