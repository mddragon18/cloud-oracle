"""Streamlit Cloud check: run from the repo root in a venv with ONLY service/dashboard/requirements.txt.

    python service/dashboard/check_cloud.py

Renders the dashboard with AppTest (no ORACLE_API_URL, no secrets) and asserts it falls back to embedded mode
(the recorded AWS run, processed in-process), every panel shows, the honesty badges and banner are on, there are
no error boxes or exceptions, and the what-if form works.
"""
import os
import sys

from streamlit.testing.v1 import AppTest

os.environ.pop("ORACLE_API_URL", None)
for mod in ("fastapi", "boto3", "statsmodels", "matplotlib"):
    sys.modules[mod] = None  # make any import of these fail loudly: Cloud won't have them

at = AppTest.from_file("service/dashboard/app.py", default_timeout=60).run()
assert not at.exception, at.exception
assert not at.error, [e.value for e in at.error]
assert at.toggle[0].value is True, "should start in offline mode"
md = " ".join(m.value for m in at.markdown)
assert "Cloud backend offline: running the same code on recorded AWS data" in md, "missing embedded badge"
assert "Replay of recorded run (2026-11-05)" in md and "Recorded run" in md
assert any("Low confidence" in w.value for w in at.warning), "short recorded run must show the low-confidence banner"
sub = " ".join(s.value for s in at.subheader)
for panel in ("Forecast vs actual", "Model accuracy (offline evaluation)", "Options for peak", "What-if", "History (7 days)"):
    assert panel in sub, f"missing panel {panel!r}"
assert "<h1>Scale " in md and "Recommended" in md and "Options for peak 268 req/min" in sub
assert len(at.get("plotly_chart")) >= 3, "expected rpm, CPU and memory charts"
countdown = [x.value for x in (*at.success, *at.warning, *at.error) if "CPU" in x.value or "exhaustion" in x.value]
assert countdown, "missing exhaustion countdown"

at.number_input[0].set_value(500).run()
next(b for b in at.button if b.label == "Plan for this load").click().run()
assert not at.exception, at.exception
assert any("vs current" in m.value for m in at.markdown), "what-if result missing"
print("cloud check OK:", len(at.subheader), "panels,", "countdown =", countdown[0])
