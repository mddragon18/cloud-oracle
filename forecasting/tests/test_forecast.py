import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from forecasting.forecast import forecast, load_metrics

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_c2(result):
    assert result["horizon_minutes"] == 1440
    assert result["step_minutes"] == 15
    assert len(result["series"]) == 96
    for key in ("timestamp", "requests_per_min", "cpu_pct", "mem_pct", "lower", "upper"):
        assert key in result["series"][-1], key
    assert {"mape_pct", "rmse"} <= set(result["accuracy"])
    assert result["cpu_threshold_pct"] == 70


def test_sample():
    """2-row contract sample: stdlib-only trend fallback, no accuracy (nothing held out)."""
    result = forecast(load_metrics(os.path.join(HERE, "contracts", "C1-metrics.sample.csv")))
    check_c2(result)
    assert result["model"] == "naive"
    assert result["accuracy"] == {"mape_pct": None, "rmse": None}
    assert result["series"][0]["timestamp"] == "2026-10-25T10:16:00Z"


def test_naive_does_not_run_away():
    """Regression: 20 noisy real-like minutes used to extrapolate to ~85k rpm over 24 h."""
    from forecasting.synthetic import generate
    rows = generate("steady", days=1).head(20).to_dict("records")
    rows[-1]["requests_per_min"] *= 1.5  # one noisy last minute
    result = forecast(rows)
    check_c2(result)
    assert result["model"] == "naive"
    observed_max = max(r["requests_per_min"] for r in rows)
    assert all(r["upper"] <= observed_max * 1.5 for r in result["series"]), result["series"][0]
    assert len({r["requests_per_min"] for r in result["series"]}) == 1  # flat
    assert result["exhaustion_at"] is None


def test_arima_cycle():
    from forecasting.synthetic import generate
    result = forecast(generate("cycle", days=4))  # DataFrame input
    check_c2(result)
    assert result["model"] == "arima"
    assert result["accuracy"]["mape_pct"] < 5, result["accuracy"]
    assert all(r["lower"] <= r["requests_per_min"] <= r["upper"] for r in result["series"])
    assert result["exhaustion_at"] is None  # cycle peaks ~800 rpm -> ~22% CPU


def test_growth_exhaustion():
    from forecasting.synthetic import generate
    # ends ~1000 rpm (~27% CPU at the measured 2.7%/100 rpm), +100 rpm/day -> crosses 28% next day
    result = forecast(generate("growth", days=7), cpu_threshold_pct=28)
    assert result["exhaustion_at"] is not None
    hit = next(r for r in result["series"] if r["timestamp"] == result["exhaustion_at"])
    assert hit["cpu_pct"] >= 28


def test_instances_are_summed():
    import pandas as pd
    from forecasting.synthetic import generate
    a = generate("steady", days=3, seed=1)
    b = generate("steady", days=3, seed=2).assign(instance_id="i-02")
    one, two = forecast(a), forecast(pd.concat([a, b]))
    ratio = two["series"][0]["requests_per_min"] / one["series"][0]["requests_per_min"]
    assert 1.8 < ratio < 2.2, ratio


def test_latest_stretch_with_lost_server():
    """Regression for the Nov-7 284% MAPE: an old run 2 days earlier must not count as history
    (the gap was interpolated into fake data), and a server that stops reporting is not a demand drop."""
    import pandas as pd
    from forecasting.synthetic import generate
    old = generate("steady", days=1, start="2026-11-05T00:00:00Z")
    servers = [generate("steady", days=1, start="2026-11-07T00:00:00Z", seed=s).head(10 * 60)
               .assign(instance_id=f"i-0{s}") for s in (1, 2, 3)]
    servers[0] = servers[0].head(6 * 60)  # i-01 stops reporting after 6 h; the others keep their share
    result = forecast(pd.concat([old, *servers]))
    check_c2(result)
    assert result["model"] == "arima-short", result["model"]  # 10 h stretch: no daily cycle, no 2-day ARIMA
    assert result["accuracy"]["holdout_minutes"] == 180
    assert result["accuracy"]["mape_pct"] < 10, result["accuracy"]
    level = result["series"][0]["requests_per_min"]
    assert 1350 < level < 1650, level  # 3 x ~500 rpm, not 2 x 500 after i-01 went quiet
    assert all(r["requests_per_min"] < 2000 for r in result["series"])  # no trend runaway

    # the other case (Nov 4): the one server left takes over everyone's traffic -> no scaling
    from forecasting.forecast import latest_stretch
    took_over = servers[1].head(6 * 60 + 60).copy()
    took_over.iloc[6 * 60:, took_over.columns.get_loc("requests_per_min")] *= 3
    pts = latest_stretch(pd.concat([servers[0], servers[2].head(6 * 60), took_over]).to_dict("records"))
    assert 1350 < pts[-1][1] < 1650, pts[-1][1]  # ~3 x 500, not 9 x 500


def test_sliding_window():
    """forecast() uses only the last `window` hours, and picks the model by what is left."""
    from forecasting.forecast import latest_stretch
    from forecasting.synthetic import generate
    week = generate("cycle", days=7)
    pts = latest_stretch(week.to_dict("records"), window_hours=72)
    assert (pts[-1][0] - pts[0][0]).total_seconds() / 3600 < 72 <= len(pts) / 60 + 0.1  # old rows trimmed

    r = forecast(week, window=72)
    assert r["model"] == "arima" and r["window_hours"] == 72 and r["accuracy"]["holdout_minutes"] == 1440
    assert forecast(week, window=48)["model"] == "arima-short"  # 48 h can never reach the 2-day model
    assert forecast(week, window=7)["model"] == "arima-short"
    assert forecast(week, window=5)["model"] == "naive"

    # a gap inside the window: only the stretch after it counts (8 h -> arima-short, not 3-day arima)
    gappy = week[(week["timestamp"] < "2026-10-07T00:00:00Z") | (week["timestamp"] >= "2026-10-07T16:00:00Z")]
    assert forecast(gappy, window=72)["model"] == "arima-short"


def test_diverged_fit_falls_back():
    """Regression: an ARIMA fit on Azure (671-728 rpm) once forecast 1.1 million rpm."""
    import numpy as np
    import forecasting.forecast as f
    from forecasting.synthetic import generate
    real = f._fit_predict
    f._fit_predict = lambda y, steps, period, daily=True: (np.full(steps, 1.1e6), np.zeros(steps), np.zeros(steps))
    try:
        r = forecast(generate("steady", days=3))
    finally:
        f._fit_predict = real
    assert r["model"] == "naive" and max(s["requests_per_min"] for s in r["series"]) < 1000, r["model"]


def test_backtest():
    """Walk-forward: each origin only sees the past; horizons beyond the data stay empty."""
    from forecasting.backtest import run, summarize
    from forecasting.synthetic import generate
    res = run(generate("steady", days=1).head(9 * 60), window=72, step_minutes=60, warmup_hours=6)
    assert list(res["origin"]) == ["2026-10-01T06:00:00Z", "2026-10-01T07:00:00Z", "2026-10-01T08:00:00Z"]
    assert list(res["model"]) == ["naive", "arima-short", "arima-short"]  # 06:00 sees 5 h 59 min
    assert res["mape_1h"].notna().all() and res["mape_1h"].max() < 10, res["mape_1h"]
    assert res["mape_6h"].isna().all() and res["baseline_1h"].isna().all()  # no future 6 h, no yesterday
    s = summarize(res, "t", 72, 60, 6)
    assert s["horizons"]["1h"]["n"] == 3 and s["horizons"]["24h"]["n"] == 0


def test_loaders():
    import pandas as pd
    from forecasting.loaders import azure_functions, wikipedia
    hourly = pd.Series([100.0, 200.0, 400.0],
                       index=pd.date_range("2026-10-01", periods=3, freq="h", tz="UTC"))
    w = wikipedia(hourly=hourly, peak_rpm=1000)
    assert len(w) == 180 and w["requests_per_min"].max() == 1000
    assert w["timestamp"].iloc[0] == "2026-10-01T00:00:00Z"

    with tempfile.TemporaryDirectory() as d:
        cols = ["HashOwner", "HashApp", "HashFunction", "Trigger"] + [str(m) for m in range(1, 1441)]
        for day in (1, 2):
            rows = [["o", "a", "f-http", "http"] + [day] * 1440,
                    ["o", "a", "f-timer", "timer"] + [999] * 1440]
            pd.DataFrame(rows, columns=cols).to_csv(
                os.path.join(d, f"invocations_per_function_md.anon.d0{day}.csv"), index=False)
        az = azure_functions(d, peak_rpm=1000)
    assert len(az) == 2880
    assert az["requests_per_min"].iloc[0] == 500 and az["requests_per_min"].iloc[-1] == 1000

    from forecasting.loaders import aws_run
    from forecasting.synthetic import generate
    sample = generate("steady", days=1).head(10)
    with tempfile.TemporaryDirectory() as d:  # collector re-uploads its growing csv: files overlap
        os.makedirs(os.path.join(d, "i-01"))
        sample.head(5).to_csv(os.path.join(d, "i-01", "metrics-1.csv"), index=False)
        sample.to_csv(os.path.join(d, "i-01", "metrics-2.csv"), index=False)
        run = aws_run(d)
    assert len(run) == 10 and run["timestamp"].is_monotonic_increasing


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name} OK")
    print("test_forecast OK")
