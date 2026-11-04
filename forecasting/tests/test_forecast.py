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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"{name} OK")
    print("test_forecast OK")
