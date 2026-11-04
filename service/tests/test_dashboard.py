import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
import app as dash
from client import Client

from service.oracle_service.config import REPO

NOW = datetime(2026, 10, 25, 10, 15, tzinfo=UTC)
C3 = json.loads((REPO / "contracts/C3-plan.sample.json").read_text())


def test_countdown_null_and_levels():
    assert dash.countdown(None, 70, NOW) == ("No exhaustion in the next 24 h", "ok")
    assert dash.countdown("2026-10-25T18:45:00Z", 70, NOW) == ("CPU reaches 70% in 8 h 30 min (18:45 UTC)", "ok")
    assert dash.countdown("2026-10-25T13:00:00Z", 70, NOW)[1] == "warning"
    assert dash.countdown("2026-10-25T10:45:00Z", 70, NOW)[1] == "critical"


def test_accuracy_null():
    assert "not enough history yet" in dash.accuracy_text({"model": "arima", "accuracy": {"mape_pct": None, "rmse": None}})
    assert "MAPE 8.4%" in dash.accuracy_text({"model": "lstm", "accuracy": {"mape_pct": 8.4, "rmse": 42.1}})


def test_cards_and_delta():
    card = dash.option_card_html(C3["options"][0], True)
    assert "6 × t3.micro" in card and "Recommended" in card and "&#36;1.61" in card and "$" not in card
    assert dash.headline(C3) == "Scale out to 6 × t3.micro"
    assert "&#36;1.61" in dash.kpi_html(C3) and "5,000" in dash.kpi_html(C3)
    assert "vs current" in dash.delta_text(C3)
    assert dash.age_text("2026-10-25T10:08:00Z", NOW) == "updated 7 min ago"


def test_offline_client():
    c = Client(None)
    assert c.plan()[1] == "sample" and len(c.whatif(500)["options"]) == 2 and c.history() == []


def test_unreachable_api():
    import pytest
    from client import ApiError
    with pytest.raises(ApiError, match="unreachable"):
        Client("http://127.0.0.1:9").plan()


def test_page_renders_offline():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert any("Scale out to" in m.value for m in at.markdown)


def test_confidence_texts_and_offline_quality():
    assert dash.low_confidence_text(20) == "Low confidence: only 20 rows of history, simple model; numbers may be unrealistic"
    assert dash.data_age_text(60) == "newest metrics 1 h 0 min old" and dash.data_age_text(None) == "data age unknown"
    _, src, q = Client(None).forecast()  # demo shift makes the sample current
    assert src == "sample" and q["confidence"] == "normal" and q["data_age_minutes"] <= 1


def test_demo_shift_countdown_reads_normally():
    now = datetime(2026, 12, 15, 9, 0, tzinfo=UTC)
    c = Client(None, now=now)
    c2, src, q = c.forecast()
    c3, _ = c.plan()
    rows = c.recent()
    # sample: newest row 10:15, exhaustion 18:45 -> 8 h 30 min ahead of the shifted "now"
    assert c2["series"][0]["timestamp"] == "2026-12-15T09:15:00Z" and c2["exhaustion_at"] == "2026-12-15T17:30:00Z"
    assert c3["exhaustion_at"] == c2["exhaustion_at"] and rows[-1]["timestamp"] == "2026-12-15T08:46:00Z"
    assert dash.countdown(c2["exhaustion_at"], 70, now) == ("CPU reaches 70% in 8 h 30 min (17:30 UTC)", "ok")
    assert src == "sample" and q == {"confidence": "normal", "data_age_minutes": 0}
    assert json.loads((REPO / "contracts/C2-forecast.sample.json").read_text())["exhaustion_at"] == "2026-10-25T18:45:00Z"


def test_live_mode_not_shifted():
    from datetime import timedelta

    from client import shift_times
    doc = {"generated_at": "2026-10-25T10:15:00Z", "exhaustion_at": None, "series": [{"timestamp": "2026-10-25T10:30:00Z"}]}
    assert Client("http://x")._demo(doc) is doc  # live: untouched object
    assert Client(None)._demo(doc, "live") is doc  # stored local results: untouched
    assert shift_times(doc, timedelta(hours=1))["exhaustion_at"] is None


def test_runway_marks_crossing():
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    assert "left:25.0%" in dash.runway_html("2026-10-25T18:00:00Z", 1440, now, 70)
    assert "no crossing" in dash.runway_html(None, 1440, now, 70)
    past = dash.runway_html("2026-10-25T11:00:00Z", 1440, now, 70)  # past -> mark at now, label pinned left
    assert 'style="left:0.0%"' in past and "exceeded at 11:00 UTC" in past and "left:0;transform:none" in past
    assert "right:0" in dash.runway_html("2026-10-26T11:00:00Z", 1440, now, 70)  # near the end -> pinned right
