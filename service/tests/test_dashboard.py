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


def test_page_renders_offline(monkeypatch):
    import client  # the module app.py imports (service/dashboard is on sys.path)
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(client, "RECORDED", [])  # no recorded run -> the contract-sample demo
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
    assert src == "sample" and q == {"confidence": "normal", "data_age_minutes": 0, "replay_at": None}
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


def test_compare_line_from_plan_numbers():
    s = dash.compare_html(C3)
    assert s == ("&#36;1.61/day against &#36;4.30/day to scale up · 52 ms expected latency against 47 ms · "
                 "no single point of failure")


def test_sparse_note():
    assert dash.sparse_note(1, 2) == ("This data has 1 forecast point and 2 metric rows, so the chart shows points "
                                      "rather than lines. Live data fills the next 24 h.")
    assert dash.sparse_note(96, 18) is None and dash.sparse_note(1, 18) is None


def test_accuracy_table_parses_main_table_only(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# t\n\n| dataset | model | MAE (req/min) | RMSE | MAPE % |\n|---|---|---|---|---|\n"
                 "| wikipedia | arima | 1 | 2 | 3.28 |\n| wikipedia | same-time-yesterday | 1 | 2 | 4.68 |\n"
                 "| wikipedia | lstm (Colab run) | 1 | 2 | 4.10 |\n| azure | arima | 1 | 2 | 1.32 |\n\n"
                 "## later\n| dataset | model | MAE | RMSE | MAPE % |\n| other | arima | 1 | 2 | 9 |\n")
    assert dash.accuracy_table(f) == [{"dataset": "wikipedia", "arima": 3.28, "same-time-yesterday": 4.68, "lstm": 4.10},
                                      {"dataset": "azure", "arima": 1.32}]


def test_accuracy_table_missing_or_unrelated_file_hides_panel(tmp_path):
    assert dash.accuracy_table(tmp_path / "nope.md") == []
    (tmp_path / "x.md").write_text("no table here")
    assert dash.accuracy_table(tmp_path / "x.md") == []


def test_break_gaps_only_over_five_minutes():
    rows = [{"timestamp": f"2026-11-05T10:{m:02d}:00Z", "requests_per_min": 1.0} for m in (0, 5, 11)]
    out = dash.break_gaps(rows)
    assert [r["requests_per_min"] for r in out] == [1.0, 1.0, None, 1.0]
    assert out[2]["timestamp"] == rows[2]["timestamp"]


def test_embedded_runs_recorded_aws_data_without_aws(monkeypatch):
    import service.dashboard.client as cl
    monkeypatch.setattr(cl, "_embedded_env", None)
    monkeypatch.setattr(cl.requests, "request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no HTTP")))
    c = Client(None, embedded=True)
    c2, src, q = c.forecast()
    c3, _ = c.plan()
    assert src == "embedded" and q["replay_at"] == "2026-11-05T11:19:00Z" and q["data_age_minutes"] == 0
    assert c3["peak_requests_per_min"] == 268 and c3["options"][0] == {**c3["options"][0], "instances": 2,
                                                                         "instance_type": "t3.micro"}
    assert len(c.recent(24)) == 155 and len(c.history(7)) == 1 and c.whatif(500)["options"]
    assert Client(None).forecast()[1] == "sample"  # the sample demo still reads the sample afterwards


def test_api_alive_needs_health_within_timeout(monkeypatch):
    import service.dashboard.client as cl
    assert not cl.api_alive("")
    seen = {}

    def fake_get(url, timeout):
        seen.update(url=url, timeout=timeout)
        raise cl.requests.Timeout()
    monkeypatch.setattr(cl.requests, "get", fake_get)
    assert not cl.api_alive("http://x/") and seen == {"url": "http://x/health", "timeout": 3}
    monkeypatch.setattr(cl.requests, "get", lambda url, timeout: type("R", (), {"ok": True})())
    assert cl.api_alive("http://x")
