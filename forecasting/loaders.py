"""Public traces -> C1-shaped DataFrames (one row per minute).

- Wikipedia pageviews: hourly totals from the Wikimedia REST API.
- Azure Functions 2019 trace: invocations per minute per function, 14 daily files
  (invocations_per_function_md.anon.d01..d14.csv), from
  https://github.com/Azure/AzurePublicDataset/blob/master/AzureFunctionsDataset2019.md
  (the Azure VM CPU trace needs ~160 GB to get one VM over several days, so we use this).

Both are rescaled so their peak equals `peak_rpm` (our app's range) and CPU etc. are
derived with synthetic.c1_from_rpm, so the result is drop-in C1 data.
"""
import glob
import json
import os
import urllib.request

import pandas as pd

from forecasting.synthetic import c1_from_rpm

WIKI_URL = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/"
            "{project}/all-access/user/hourly/{start}00/{end}23")
USER_AGENT = "cloud-oracle-student-project (github.com/mddragon18/cloud-oracle)"


def _scale(rpm, peak_rpm):
    return rpm * (peak_rpm / rpm.max()) if rpm.max() > 0 else rpm


def wikipedia_hourly(project="en.wikipedia", start="20261001", end="20261014"):
    """Hourly pageviews as a Series indexed by UTC hour. start/end: YYYYMMDD inclusive."""
    req = urllib.request.Request(WIKI_URL.format(project=project, start=start, end=end),
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        items = json.load(resp)["items"]
    idx = pd.to_datetime([i["timestamp"] for i in items], format="%Y%m%d%H", utc=True)
    return pd.Series([float(i["views"]) for i in items], index=idx, name="views")


def wikipedia(project="en.wikipedia", start="20261001", end="20261014", peak_rpm=1000, hourly=None):
    """C1 DataFrame from Wikipedia hourly pageviews, linearly interpolated to minutes.
    Pass `hourly` (Series from wikipedia_hourly) to skip the network call."""
    if hourly is None:
        hourly = wikipedia_hourly(project, start, end)
    minutes = pd.date_range(hourly.index[0], hourly.index[-1] + pd.Timedelta(minutes=59), freq="min")
    rpm = hourly.reindex(minutes).interpolate(method="time").ffill()
    return c1_from_rpm(_scale(rpm, peak_rpm), "wikipedia")


def azure_functions(trace_dir, trigger="http", function=None, start="2026-10-01T00:00:00Z", peak_rpm=1000):
    """C1 DataFrame for one function of the Azure Functions 2019 trace.

    trace_dir holds invocations_per_function_md.anon.d*.csv. By default picks the
    `trigger` function with the most invocations that appears in every day file.
    """
    files = sorted(glob.glob(os.path.join(trace_dir, "invocations_per_function_md.anon.d*.csv")))
    if not files:
        raise FileNotFoundError(f"no invocations_per_function_md.anon.d*.csv in {trace_dir}")
    minute_cols = [str(m) for m in range(1, 1441)]
    days = []
    for f in files:
        d = pd.read_csv(f)
        d = d[d["Trigger"] == trigger] if function is None else d
        days.append(d.set_index("HashFunction")[minute_cols])
    if function is None:
        common = set(days[0].index).intersection(*(set(d.index) for d in days[1:]))
        if not common:
            raise ValueError(f"no {trigger!r} function present in all {len(files)} day files")
        function = days[0].loc[list(common)].sum(axis=1).idxmax()
    # duplicate hashes across owners are possible; sum them as one function
    values = pd.concat([d.loc[[function]].sum(axis=0) for d in days]).to_numpy(dtype=float)
    idx = pd.date_range(start, periods=len(values), freq="min")
    return c1_from_rpm(_scale(pd.Series(values, index=idx), peak_rpm), "azure-functions")


if __name__ == "__main__":
    import argparse
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = argparse.ArgumentParser(description="write a public trace as C1 csv into data/")
    sub = p.add_subparsers(dest="src", required=True)
    w = sub.add_parser("wikipedia")
    w.add_argument("--start", default="20261001")
    w.add_argument("--end", default="20261014")
    a = sub.add_parser("azure")
    a.add_argument("trace_dir")
    args = p.parse_args()
    df = wikipedia(start=args.start, end=args.end) if args.src == "wikipedia" else azure_functions(args.trace_dir)
    out = os.path.join(here, "data", f"{args.src}.csv")
    df.to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} rows)")
