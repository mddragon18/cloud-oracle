"""Walk-forward backtest: replay a metrics history the way the 15-minute schedule sees it.

At every origin (each --step minutes) forecast() gets only the rows before that moment,
trimmed to the sliding window exactly as in production. Its forecast is scored against
what really came next: MAPE over the next 1 h, 6 h and 24 h (a horizon is left empty
while the data doesn't reach that far). The baseline on the same targets is "same time
yesterday". Unlike the per-run accuracy in C2 (each run checking itself on the hours
just before it), every number here is scored on data the forecast had not seen.

    python -m forecasting.backtest data/wikipedia.csv --window 72 --step 15 --warmup 72
    python -m forecasting.backtest data/aws-s3-nov7 --name aws-nov7 --warmup 6

Writes forecasting/results/backtest/<name>-w<window>.csv/.png/.json and rebuilds
forecasting/results/backtest.md from every .json there.
"""
import argparse
import bisect
import glob
import json
import os
from datetime import timedelta

import pandas as pd

from forecasting.forecast import _parse, errors, forecast, latest_stretch

HORIZONS_H = (1, 6, 24)
BUCKET = "15min"  # forecast() steps; --step only sets how often a forecast is made
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "results", "backtest")


def load(paths):
    """C1 csv files and/or folders of them (e.g. an `aws s3 sync` of metrics/) -> one DataFrame.
    The collector re-uploads its growing csv, so overlapping rows are dropped."""
    files = []
    for p in paths:
        files += glob.glob(os.path.join(p, "**", "*.csv"), recursive=True) if os.path.isdir(p) else [p]
    df = pd.concat(pd.read_csv(f) for f in files).drop_duplicates()
    return df.sort_values(["timestamp", "instance_id"]).reset_index(drop=True)


def run(df, window, step_minutes=15, warmup_hours=6.0, horizons=HORIZONS_H):
    """One row per origin: model used, MAPE at each horizon, and the baseline's MAPE on the same targets."""
    rows = df.to_dict("records")
    points = latest_stretch(rows)  # whole history: the "what really happened" series
    first = points[0][0]
    rows = [r for r in rows if _parse(r["timestamp"]) >= first]  # same stretch for the forecasts
    stamps = [r["timestamp"] for r in rows]  # ISO 'Z' strings sort in time order
    actual = (pd.Series([p[1] for p in points], index=pd.DatetimeIndex([p[0] for p in points]))
              .resample(BUCKET).mean())
    step = pd.Timedelta(minutes=step_minutes)
    origin = (pd.Timestamp(first) + pd.Timedelta(hours=warmup_hours)).ceil(BUCKET)
    out = []
    while origin <= actual.index[-1]:
        lo = bisect.bisect_left(stamps, (origin - timedelta(hours=window + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        hi = bisect.bisect_left(stamps, origin.strftime("%Y-%m-%dT%H:%M:%SZ"))
        fc = forecast(rows[lo:hi], window=window)
        # a forecast point belongs to the 15-min bucket it falls in (naive points sit mid-bucket)
        pred = pd.Series([s["requests_per_min"] for s in fc["series"]],
                         index=pd.DatetimeIndex([s["timestamp"] for s in fc["series"]]).floor(BUCKET))
        rec = {"origin": origin.strftime("%Y-%m-%dT%H:%M:%SZ"), "model": fc["model"]}
        for h in horizons:
            targets = pd.date_range(origin, periods=h * 4, freq=BUCKET)
            a = actual.reindex(targets)
            base = actual.reindex(targets - pd.Timedelta(days=1))
            if a.isna().any():  # data ends before this horizon
                rec[f"mape_{h}h"] = rec[f"baseline_{h}h"] = None
                continue
            rec[f"mape_{h}h"] = errors(a.to_numpy(), pred.reindex(targets).to_numpy())["mape_pct"]
            rec[f"baseline_{h}h"] = None if base.isna().any() else errors(a.to_numpy(), base.to_numpy())["mape_pct"]
        out.append(rec)
        origin += step
    return pd.DataFrame(out)


def summarize(res, name, window, step_minutes, warmup_hours, horizons=HORIZONS_H):
    s = {"dataset": name, "window_hours": window, "step_minutes": step_minutes, "warmup_hours": warmup_hours,
         "origins": len(res), "first_origin": res["origin"].iloc[0], "last_origin": res["origin"].iloc[-1],
         "models": res["model"].value_counts().to_dict(), "horizons": {}}
    for h in horizons:
        both = res[[f"mape_{h}h", f"baseline_{h}h"]].dropna()  # baseline needs a day of history: compare like for like
        m = res[f"mape_{h}h"].dropna()
        s["horizons"][f"{h}h"] = {
            "n": int(len(m)), "mape_mean": round(float(m.mean()), 2) if len(m) else None,
            "mape_median": round(float(m.median()), 2) if len(m) else None,
            "n_with_baseline": int(len(both)),
            "mape_mean_where_baseline": round(float(both[f"mape_{h}h"].mean()), 2) if len(both) else None,
            "baseline_mean": round(float(both[f"baseline_{h}h"].mean()), 2) if len(both) else None}
    return s


def chart(res, path, title, horizons=HORIZONS_H):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = pd.to_datetime(res["origin"])
    horizons = [h for h in horizons if res[f"mape_{h}h"].notna().any()]  # no empty panels
    fig, axes = plt.subplots(len(horizons), 1, figsize=(10, 2.4 * len(horizons)), sharex=True, squeeze=False)
    for ax, h in zip(axes[:, 0], horizons):
        ax.plot(t, res[f"mape_{h}h"], color="#2a78d6", lw=1.5, label="forecast()")
        if res[f"baseline_{h}h"].notna().any():
            ax.plot(t, res[f"baseline_{h}h"], color="#eb6834", lw=1.5, label="same time yesterday")
        ax.set_ylabel(f"MAPE %, next {h} h", fontsize=8)
        ax.grid(axis="y", color="#e6e5e0", lw=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(labelsize=7)
    axes[0, 0].legend(fontsize=8, frameon=False, loc="upper right")
    axes[0, 0].set_title(title, fontsize=10, loc="left")
    axes[-1, 0].set_xlabel("forecast made at (UTC)", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_index():
    """results/backtest.md: one table over every saved summary."""
    lines = ["# Walk-forward backtest (sliding window)", "",
             "Each origin: `forecast()` sees only the rows before it, trimmed to the window, and is scored on",
             "what came next. Baseline columns are \"same time yesterday\" on the same origins (they need a",
             "day of history, so they can cover fewer origins). Reproduce with the command in",
             "`forecasting/backtest.py`.", "",
             "| dataset | window | origins | horizon | MAPE % mean (median) | where baseline exists: forecast vs baseline | models used |",
             "|---|---|---|---|---|---|---|"]
    summaries = []
    for f in glob.glob(os.path.join(OUT_DIR, "*.json")):
        with open(f) as fh:
            summaries.append(json.load(fh))
    for s in sorted(summaries, key=lambda s: (s["dataset"], s["window_hours"])):
        models = ", ".join(f"{k} {v}" for k, v in s["models"].items())
        for h, v in s["horizons"].items():
            if not v["n"]:
                continue
            vs = (f"{v['mape_mean_where_baseline']:.2f} vs {v['baseline_mean']:.2f} (n={v['n_with_baseline']})"
                  if v["n_with_baseline"] else "n/a")
            lines.append(f"| {s['dataset']} | {s['window_hours']:g} h | {s['origins']} | {h} | "
                         f"{v['mape_mean']:.2f} ({v['mape_median']:.2f}) | {vs} | {models} |")
    with open(os.path.join(HERE, "results", "backtest.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("data", nargs="+", help="C1 csv files and/or folders of them")
    p.add_argument("--name", help="dataset name for the output files (default: first file's name)")
    p.add_argument("--window", type=float, default=None, help="hours (default: FORECAST_WINDOW_HOURS or 72)")
    p.add_argument("--step", type=int, default=15, help="minutes between origins")
    p.add_argument("--warmup", type=float, default=6.0,
                   help="hours of data before the first origin; use the largest window when comparing windows")
    a = p.parse_args(argv)
    from forecasting.forecast import window_hours
    window = a.window or window_hours()
    name = a.name or os.path.splitext(os.path.basename(a.data[0].rstrip("/\\")))[0]
    res = run(load(a.data), window, a.step, a.warmup)
    if res.empty:
        raise SystemExit("no origins: data shorter than --warmup plus one step")
    os.makedirs(OUT_DIR, exist_ok=True)
    stem = os.path.join(OUT_DIR, f"{name}-w{window:g}")
    res.to_csv(stem + ".csv", index=False)
    s = summarize(res, name, window, a.step, a.warmup)
    with open(stem + ".json", "w") as fh:
        json.dump(s, fh, indent=2)
    chart(res, stem + ".png", f"{name}: forecast error by horizon, {window:g} h window, "
                              f"origin every {a.step} min")
    write_index()
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
