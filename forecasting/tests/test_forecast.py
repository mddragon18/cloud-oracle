import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from forecasting.forecast import forecast, load_metrics

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sample():
    metrics = load_metrics(os.path.join(HERE, "contracts", "C1-metrics.sample.csv"))
    result = forecast(metrics)
    assert result["horizon_minutes"] == 1440
    assert result["step_minutes"] == 15
    assert len(result["series"]) == 96
    for key in ("timestamp", "requests_per_min", "cpu_pct", "mem_pct", "lower", "upper"):
        assert key in result["series"][-1], key
    assert {"mape_pct", "rmse"} <= set(result["accuracy"])
    assert result["cpu_threshold_pct"] == 70
    print("test_forecast OK")


if __name__ == "__main__":
    test_sample()
