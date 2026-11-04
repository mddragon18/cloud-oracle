"""Oracle dashboard (HANDOFF §8 W3). Run: streamlit run service/dashboard/app.py"""
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import ApiError, Client

ACTUAL, FORECAST, THRESHOLD = "#2a78d6", "#52514e", "#b3261e"  # palette slot 1; forecast in secondary ink


# ---------- pure helpers (tested in service/tests/test_dashboard.py) ----------
def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def duration(minutes: float) -> str:
    m = max(0, round(minutes))
    d, rem = divmod(m, 1440)
    h, mm = divmod(rem, 60)
    return " ".join(p for p in (f"{d} d" if d else "", f"{h} h" if h else "", f"{mm} min") if p)


def age_text(generated_at: str | None, now: datetime) -> str:
    if not generated_at:
        return "update time unknown"
    return f"updated {duration((now - parse(generated_at)).total_seconds() / 60)} ago"


def accuracy_text(c2: dict) -> str:
    acc = c2.get("accuracy") or {}
    if acc.get("mape_pct") is None:
        return f"{c2.get('model', '?')} · not enough history yet"
    rmse = f", RMSE {acc['rmse']:.1f}" if acc.get("rmse") is not None else ""
    return f"{c2.get('model', '?')} · MAPE {acc['mape_pct']:.1f}%{rmse}"


def countdown(exhaustion_at: str | None, threshold: float, now: datetime) -> tuple[str, str]:
    """-> (text, level) with level in ok | warning | critical."""
    if not exhaustion_at:
        return "No exhaustion in the next 24 h", "ok"
    left = (parse(exhaustion_at) - now).total_seconds() / 60
    when = parse(exhaustion_at).strftime("%H:%M UTC")
    if left <= 0:
        return f"CPU passed {threshold:g}% at {when}", "critical"
    level = "critical" if left < 60 else "warning" if left < 360 else "ok"
    return f"CPU reaches {threshold:g}% in {duration(left)} ({when})", level


def option_lines(o: dict) -> list[str]:
    return [f"**{o['instances']} × {o['instance_type']}**",
            f"${o['usd_per_hour']:.3f}/h · **${o['usd_per_day']:.2f}/day**",
            f"expected latency {o['expected_latency_ms']:g} ms",
            "single point of failure: " + ("**yes**" if o["single_point_of_failure"] else "no")]


def delta_text(c3: dict) -> str:
    cur = c3["current"]["usd_per_hour"] * 24
    rec = next(o for o in c3["options"] if o["strategy"] == c3["recommendation"])
    diff = rec["usd_per_day"] - cur
    return (f"Recommended {rec['strategy'].replace('_', '-')} costs ${rec['usd_per_day']:.2f}/day, "
            f"{'+' if diff >= 0 else '−'}${abs(diff):.2f}/day vs current ({c3['current']['instances']} × "
            f"{c3['current']['instance_type']}).")


# ---------- rendering ----------
def main():
    import pandas as pd
    import plotly.graph_objects as go
    import streamlit as st

    st.set_page_config(page_title="Capacity Oracle", layout="wide")

    def default_url() -> str:
        if os.environ.get("ORACLE_API_URL"):
            return os.environ["ORACLE_API_URL"]
        # touching st.secrets without a secrets.toml renders an error box, so check first
        paths = (Path.cwd() / ".streamlit/secrets.toml", Path.home() / ".streamlit/secrets.toml")
        return st.secrets.get("ORACLE_API_URL", "") if any(p.exists() for p in paths) else ""

    with st.sidebar:
        st.header("Capacity Oracle")
        offline = st.toggle("Offline mode", value=not default_url(),
                            help="Call the service code directly instead of the API")
        url = st.text_input("API URL", default_url() or "http://localhost:8000", disabled=offline)
        if st.button("Refresh"):
            st.cache_data.clear()

    client = Client(None if offline else url)

    @st.cache_data(ttl=60, show_spinner=False)
    def get(kind: str, base: str | None, arg=None):
        c = Client(base)
        return {"forecast": c.forecast, "plan": c.plan, "history": c.history, "recent": c.recent}[kind](
            *([] if arg is None else [arg]))

    base = client.base_url
    now = datetime.now(UTC)
    try:
        with st.spinner("Loading forecast and plan…"):
            c2, src = get("forecast", base)
            c3, _ = get("plan", base)
    except ApiError as e:
        st.error(f"{e}. Check the URL or switch to **Offline mode** in the sidebar.")
        st.stop()

    # 1. status strip
    st.caption(("🟡 sample data (nothing stored yet)" if src == "sample" else "🟢 live")
               + f" · {age_text(c3.get('generated_at'), now)} · {accuracy_text(c2)}")
    st.markdown(f"## Recommendation: {c3['recommendation'].replace('_', '-')}")
    st.write(c3.get("reason", ""))

    # 2. exhaustion countdown
    text, level = countdown(c2.get("exhaustion_at"), c2.get("cpu_threshold_pct", 70), now)
    {"ok": st.success, "warning": st.warning, "critical": st.error}[level](
        {"ok": "✅ ", "warning": "⚠️ ", "critical": "🛑 "}[level] + text)

    # 3. forecast vs actual
    st.subheader("Forecast vs actual")
    try:
        actual = pd.DataFrame(get("recent", base, 24))
    except ApiError as e:
        actual = pd.DataFrame()
        st.info(f"Actual metrics unavailable: {e}")
    fc = pd.DataFrame(c2["series"])

    def chart(col: str, label: str, band: bool, threshold: float | None = None):
        fig = go.Figure()
        if band:
            fig.add_trace(go.Scatter(x=list(fc.timestamp) + list(fc.timestamp[::-1]),
                                     y=list(fc.upper) + list(fc.lower[::-1]), fill="toself",
                                     fillcolor="rgba(82,81,78,0.15)", line={"width": 0},
                                     name="forecast band", hoverinfo="skip"))
        if not actual.empty:
            fig.add_trace(go.Scatter(x=actual.timestamp, y=actual[col], name="actual",
                                     line={"color": ACTUAL, "width": 2}))
        fig.add_trace(go.Scatter(x=fc.timestamp, y=fc[col], name="forecast",
                                 line={"color": FORECAST, "width": 2, "dash": "dash"}))
        if threshold is not None:
            fig.add_hline(y=threshold, line={"color": THRESHOLD, "width": 1, "dash": "dot"},
                          annotation_text=f"{threshold:g}% threshold")
        fig.update_layout(height=300, margin={"l": 0, "r": 0, "t": 10, "b": 0}, hovermode="x unified",
                          yaxis_title=label, legend={"orientation": "h", "y": 1.1})
        st.plotly_chart(fig, use_container_width=True)

    chart("requests_per_min", "requests / min", band=True)
    chart("cpu_pct", "CPU %", band=False, threshold=c2.get("cpu_threshold_pct", 70))

    # 4. options
    def cards(plan: dict):
        cols = st.columns(2)
        for col, o in zip(cols, plan["options"]):
            with col, st.container(border=True):
                rec = o["strategy"] == plan["recommendation"]
                st.markdown(f"### {o['strategy'].replace('_', '-')}" + ("  ⭐ recommended" if rec else ""))
                for line in option_lines(o):
                    st.markdown(line)

    st.subheader(f"Options for peak {c3['peak_requests_per_min']:g} req/min")
    cards(c3)
    cur = c3["current"]
    st.caption(f"Bandwidth {c3['bandwidth_mbps']:g} Mbps · storage {c3['storage_gb_30d']:g} GB in 30 days · "
               f"current {cur['instances']} × {cur['instance_type']} at ${cur['usd_per_hour']:.4f}/h")

    # 5. what-if
    st.subheader("What-if")
    with st.form("whatif"):
        rpm = st.number_input("Expected requests / min", 1, 1_000_000, 5000, step=500)
        go_ = st.form_submit_button("Plan for this load")
    if go_:
        try:
            with st.spinner("Planning…"):
                w = client.whatif(int(rpm))
            cards(w)
            st.write(delta_text(w))
        except ApiError as e:
            st.error(str(e))

    # 6. history
    st.subheader("History (7 days)")
    try:
        hist = get("history", base, 7)
    except ApiError as e:
        hist = []
        st.info(f"History unavailable: {e}")
    if not hist:
        st.info("No stored plans yet — run the pipeline (`make -C service pipeline-once`).")
    else:
        h = pd.DataFrame([{"time": p["generated_at"], "peak rpm": p["peak_requests_per_min"],
                           "recommendation": p["recommendation"],
                           "$/day": next(o["usd_per_day"] for o in p["options"]
                                         if o["strategy"] == p["recommendation"])} for p in hist])
        fig = go.Figure(go.Scatter(x=h["time"], y=h["$/day"], mode="lines+markers",
                                   line={"color": ACTUAL, "width": 2}, marker={"size": 8},
                                   name="recommended $/day"))
        fig.update_layout(height=250, margin={"l": 0, "r": 0, "t": 10, "b": 0}, yaxis_title="recommended $/day")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(h, hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
