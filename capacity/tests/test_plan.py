import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from capacity.plan import baseline, plan
from forecasting.forecast import forecast, load_metrics

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sample():
    metrics = load_metrics(os.path.join(HERE, "contracts", "C1-metrics.sample.csv"))
    fc = forecast(metrics)
    result = plan(fc, baseline(metrics))
    assert result["recommendation"] in ("scale_out", "scale_up")
    assert {o["strategy"] for o in result["options"]} == {"scale_out", "scale_up"}
    assert result["peak_requests_per_min"] > 0
    assert result["current"]["instances"] >= 1
    assert "usd_per_day" in result["options"][0]
    assert result["bandwidth_mbps"] >= 0
    print("test_plan OK")


if __name__ == "__main__":
    test_sample()
