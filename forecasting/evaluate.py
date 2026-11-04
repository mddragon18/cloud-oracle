"""Accuracy table + forecast-vs-actual chart for every dataset we have.

Each dataset: train on all but the last day, predict that day (15-min steps).
Baseline: "same time yesterday" (seasonal naive). Writes forecasting/results/
accuracy.md and forecast_vs_actual.png. Real traces are picked up from
data/wikipedia.csv and data/azure.csv if present (see loaders.py).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from forecasting.forecast import _frame, _per_minute, errors, holdout  # noqa: E402
from forecasting.synthetic import PATTERNS, generate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def datasets():
    import pandas as pd
    out = {f"synthetic-{p}": generate(p, days=7) for p in PATTERNS}
    for name in ("wikipedia", "azure"):
        path = os.path.join(ROOT, "data", f"{name}.csv")
        if os.path.exists(path):
            out[name] = pd.read_csv(path)
    return out


def main(step_minutes=15):
    period = 1440 // step_minutes
    results_dir = os.path.join(HERE, "results")
    os.makedirs(results_dir, exist_ok=True)
    data = datasets()
    lines = ["| dataset | model | MAE (req/min) | RMSE | MAPE % |", "|---|---|---|---|---|"]
    fig, axes = plt.subplots((len(data) + 1) // 2, 2, figsize=(12, 3 * ((len(data) + 1) // 2)), squeeze=False)
    for ax, (name, df) in zip(axes.flat, data.items()):
        points = _per_minute(df.to_dict("records"))
        actual, pred, err = holdout(points, step_minutes)
        rpm = _frame(points, step_minutes)["rpm"].to_numpy()
        base = errors(actual.to_numpy(), rpm[-2 * period:-period])
        for model, e in (("arima", err), ("same-time-yesterday", base)):
            mape = "n/a" if e["mape_pct"] is None else f"{e['mape_pct']:.2f}"
            lines.append(f"| {name} | {model} | {e['mae']:.1f} | {e['rmse']:.1f} | {mape} |")
        ax.plot(actual.index, actual.to_numpy(), label="actual", lw=1)
        ax.plot(actual.index, pred, label="ARIMA", lw=1)
        arima_mape = "n/a" if err["mape_pct"] is None else f"{err['mape_pct']:.1f}%"
        ax.set_title(f"{name}  (ARIMA MAPE {arima_mape})", fontsize=9)
        ax.set_ylabel("req/min")
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=7)
    for ax in list(axes.flat)[len(data):]:
        ax.axis("off")
    fig.suptitle("Held-out day: forecast vs actual")
    fig.tight_layout()
    fig.savefig(os.path.join(results_dir, "forecast_vs_actual.png"), dpi=120)
    table = "\n".join(lines) + "\n"
    with open(os.path.join(results_dir, "accuracy.md"), "w") as f:
        f.write("# Forecast accuracy (held-out last day, 15-min steps)\n\n" + table)
    print(table)


if __name__ == "__main__":
    main()
