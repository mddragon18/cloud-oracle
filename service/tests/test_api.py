import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from service.api import app as api

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sample():
    assert api.health() == {"status": "ok"}
    fc = api.latest_forecast()
    assert fc["horizon_minutes"] == 1440 and "series" in fc
    p = api.latest_plan()
    assert p["recommendation"] in ("scale_out", "scale_up")
    w = api.whatif_plan(5000)
    assert w["peak_requests_per_min"] >= 1
    assert len(w["options"]) == 2
    assert isinstance(api.history(7), list)
    print("test_api OK")


if __name__ == "__main__":
    test_sample()
