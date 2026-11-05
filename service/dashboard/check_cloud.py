"""Streamlit Cloud check: run from the repo root in a venv with ONLY service/dashboard/requirements.txt.

    python service/dashboard/check_cloud.py

Renders the dashboard with AppTest (no ORACLE_API_URL, no secrets) and asserts every panel shows,
offline/demo mode is on, there are no error boxes or exceptions, and the what-if form works.
"""
import os
import sys

from streamlit.testing.v1 import AppTest

os.environ.pop("ORACLE_API_URL", None)
for mod in ("fastapi", "boto3", "statsmodels", "matplotlib"):
    sys.modules[mod] = None  # make any import of these fail loudly: Cloud won't have them

at = AppTest.from_file("service/dashboard/app.py", default_timeout=60).run()
assert not at.exception, at.exception
assert not at.error, [e.value for e in at.error]  # demo countdown is shifted to the future: nothing red
assert at.toggle[0].value is True, "should start in offline mode"
assert any("Demo data: live API not connected yet" in i.value for i in at.info)
assert not any("Low confidence" in w.value for w in at.warning), "demo data should read as current, no banner"
md = " ".join(m.value for m in at.markdown)
sub = " ".join(s.value for s in at.subheader)
for panel in ("Forecast vs actual", "Model accuracy (offline evaluation)", "Options for peak", "What-if", "History (7 days)"):
    assert panel in sub, f"missing panel {panel!r}"
assert "Scale out to 6 × t3.micro" in md and "Recommended" in md
assert len(at.get("plotly_chart")) >= 3, "expected rpm, CPU and memory charts"
countdown = [x.value for x in (*at.success, *at.warning, *at.error) if "CPU" in x.value or "exhaustion" in x.value]
assert countdown, "missing exhaustion countdown"

at.number_input[0].set_value(500).run()
next(b for b in at.button if b.label == "Plan for this load").click().run()
assert not at.exception, at.exception
assert any("vs current" in m.value for m in at.markdown), "what-if result missing"
print("cloud check OK:", len(at.subheader), "panels,", "countdown =", countdown[0])
