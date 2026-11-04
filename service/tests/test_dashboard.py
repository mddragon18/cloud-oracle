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
    assert dash.option_lines(C3["options"][0])[0] == "**6 × t3.micro**"
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
    assert any("Recommendation" in m.value for m in at.markdown)
