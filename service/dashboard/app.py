"""Oracle dashboard (HANDOFF §8 W3). Run: streamlit run service/dashboard/app.py"""
import os
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import ApiError, Client

# Achromatic ledger (taste-skill app sheet): ink chrome; the one chart hue sits on the forecast, the main data element.
INK, MUTED, GRID, HUE, HUE_BAND = "#141414", "#6b6b6b", "#eef0f3", "#1d5fbf", "rgba(29,95,191,0.12)"
MEM_LIMIT_PCT = 85  # Member 1's AWS run: RAM, not CPU, binds on t3.micro (~620 rpm); dashboard-only marker


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


def low_confidence_text(n_rows: int | None) -> str:
    rows = f"only {n_rows} rows of history" if n_rows is not None else "little history"
    return f"Low confidence: {rows}, simple model; numbers may be unrealistic"


def data_age_text(minutes: int | None) -> str:
    return "data age unknown" if minutes is None else f"newest metrics {duration(minutes)} old"


def _usd(x: float, digits: int = 2) -> str:
    return f"&#36;{x:,.{digits}f}"  # HTML entity: Streamlit markdown treats $..$ as LaTeX


def _rec(c3: dict) -> dict:
    return next(o for o in c3["options"] if o["strategy"] == c3["recommendation"])


def headline(c3: dict) -> str:
    """The answer, as the screen's h1: 'Scale out to 6 × t3.micro'."""
    o = _rec(c3)
    verb = "Scale out" if o["strategy"] == "scale_out" else "Scale up"
    return f"{verb} to {o['instances']} × {o['instance_type']}"


def kpi_html(c3: dict) -> str:
    """Five-cell KPI strip; money in bold, everything in tabular figures."""
    o, cur = _rec(c3), c3["current"]
    cells = [("Forecast peak", f"{c3['peak_requests_per_min']:,.0f}", "req/min"),
             ("Recommended", f"<b>{_usd(o['usd_per_day'])}</b>", "/day"),
             ("Current", _usd(cur["usd_per_hour"] * 24), f"/day · {cur['instances']} × {escape(cur['instance_type'])}"),
             ("Bandwidth at peak", f"{c3['bandwidth_mbps']:,.1f}", "Mbps"),
             ("Storage in 30 days", f"{c3['storage_gb_30d']:,.1f}", "GB")]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="kpi-label">{lab}</div><div class="kpi-value">{val}'
        f'<span class="unit"> {unit}</span></div></div>' for lab, val, unit in cells) + "</div>"


def runway_html(exhaustion_at: str | None, horizon_min: int, now: datetime, threshold: float) -> str:
    """Capacity runway: the next `horizon_min` minutes as a track, with a mark where CPU crosses the threshold."""
    hours = horizon_min / 60
    if not exhaustion_at:
        return (f'<div class="runway"><div class="track"><div class="fill" style="width:100%"></div></div>'
                f'<div class="runway-scale"><span>now</span><span>+{hours:g} h: no crossing</span></div></div>')
    left = (parse(exhaustion_at) - now).total_seconds() / 60
    pct = max(0.0, min(100.0, left / horizon_min * 100))
    when = parse(exhaustion_at).strftime("%H:%M UTC")
    label = f"{threshold:g}% CPU exceeded at {when}" if left < 0 else f"{threshold:g}% CPU · {when}"
    # keep the label inside the track: pinned to an end near the edges (and the end's own label dropped), centred elsewhere
    if pct < 15:
        pos, start, end = "left:0;transform:none", "", f"+{hours:g} h"
    elif pct > 85:
        pos, start, end = "right:0;left:auto;transform:none", "now", ""
    else:
        pos, start, end = f"left:{pct:.1f}%", "now", f"+{hours:g} h"
    return (f'<div class="runway"><div class="track"><div class="fill" style="width:{pct:.1f}%"></div>'
            f'<div class="mark" style="left:{pct:.1f}%"></div></div>'
            f'<div class="runway-scale"><span>{start}</span><span class="mark-label" style="{pos}">'
            f'{label}</span><span>{end}</span></div></div>')


def option_card_html(o: dict, recommended: bool) -> str:
    name = "Scale out" if o["strategy"] == "scale_out" else "Scale up"
    tag = '<span class="pill">Recommended</span>' if recommended else ""
    spof = "yes" if o["single_point_of_failure"] else "no"
    return (f'<div class="opt{" opt-rec" if recommended else ""}"><div class="opt-head"><span class="opt-name">{name}</span>{tag}</div>'
            f'<div class="opt-size">{o["instances"]} × {escape(o["instance_type"])}</div>'
            f'<div class="opt-money"><b>{_usd(o["usd_per_day"])}</b><span class="unit"> /day</span></div>'
            f'<dl><dt>Hourly</dt><dd>{_usd(o["usd_per_hour"], 3)}</dd>'
            f'<dt>Expected latency</dt><dd>{o["expected_latency_ms"]:,.0f} ms</dd>'
            f'<dt>Single point of failure</dt><dd>{spof}</dd></dl></div>')


def delta_text(c3: dict) -> str:
    cur = c3["current"]["usd_per_hour"] * 24
    rec = _rec(c3)
    diff = rec["usd_per_day"] - cur
    return (f"Recommended {rec['strategy'].replace('_', '-')} costs \\${rec['usd_per_day']:.2f}/day, "
            f"{'+' if diff >= 0 else '−'}\\${abs(diff):.2f}/day vs current ({c3['current']['instances']} × "
            f"{c3['current']['instance_type']}).")


CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root { --ground:#f2f4f7; --surface:#fff; --raised:#eeeeee; --border:#e6e6e6; --text:#0a0a0a; --muted:#6b6b6b;
  --accent:#141414; --hue:#1d5fbf; --negative:#c4242a; --warning:#92400e; --radius-card:8px; --radius-control:6px; }
.stApp, .stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp div, .stApp span:not([data-testid="stIconMaterial"]),
.stApp button, .stApp input, .stApp label { font-family: "Geist", Inter, system-ui, sans-serif !important; }
.stApp { background: var(--ground); }
[data-testid="stHeader"] { background: transparent; height: 0; }
[data-testid="stToolbar"], [data-testid="stDecoration"], footer, #MainMenu { display: none !important; }
.block-container { max-width: 1180px; padding: 20px 24px 64px; }
[data-testid="stVerticalBlock"] { gap: 12px; }
/* cards: white sheet, 1px edge, no shadow */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { border-radius: var(--radius-card); }
div[data-testid="stVerticalBlockBorderWrapper"][style*="border"], [data-testid="stForm"] {
  background: var(--surface); border: 1px solid var(--border) !important; border-radius: var(--radius-card); box-shadow: none; }
[data-testid="stForm"] { padding: 16px 20px; }
h1, h2, h3 { letter-spacing: -0.01em; color: var(--text); }
.stApp h1 { font-size: 28px; font-weight: 600; line-height: 1.2; padding: 0; margin: 0; }
.stApp h3 { font-size: 16px !important; font-weight: 500 !important; padding: 20px 0 2px !important; }
p, li, .stMarkdown { font-size: 14px; }
[data-testid="stCaptionContainer"] { color: var(--muted); font-size: 13px; }
/* buttons: near-black primary, grey secondary, 6px radius */
.stButton button, [data-testid="stFormSubmitButton"] button, [data-testid="stPopover"] button {
  border-radius: var(--radius-control); min-height: 36px; font-weight: 500; box-shadow: none; }
[data-testid="stFormSubmitButton"] button { background: var(--accent); color: #fff; border: 1px solid var(--accent); }
[data-testid="stFormSubmitButton"] button:hover { background: #333; border-color: #333; color: #fff; }
.stButton button, [data-testid="stPopover"] button { background: #e5e5e5; border: 1px solid #e5e5e5; color: var(--text); }
.stButton button:hover, [data-testid="stPopover"] button:hover { background: #d9d9d9; border-color: #d9d9d9; color: var(--text); }
button:focus-visible { outline: 2px solid var(--hue) !important; outline-offset: 2px; }
/* alerts: flat lines with a status dot, no icon tiles */
[data-testid="stAlert"] > div { border-radius: var(--radius-control); padding: 10px 14px; border: 0; }
[data-testid="stAlert"] [data-testid="stAlertContentInfo"], [data-testid="stAlert"] [data-testid="stAlertContentSuccess"],
[data-testid="stAlert"] [data-testid="stAlertContentWarning"], [data-testid="stAlert"] [data-testid="stAlertContentError"] { font-size: 14px; }
[data-testid="stAlertDynamicIcon"], [data-testid="stAlert"] svg { display: none; }
div[role="alert"]:has([data-testid="stAlertContentInfo"]) { background: #e8ebf0; color: #3d3d3d; }
div[role="alert"]:has([data-testid="stAlertContentSuccess"]) { background: #e6f4ea; color: #04250e; }
div[role="alert"]:has([data-testid="stAlertContentWarning"]) { background: #fff4db; color: #6b3a0a; }
div[role="alert"]:has([data-testid="stAlertContentError"]) { background: #ffedea; color: #831c1e; }
/* top bar */
.bar { display:flex; align-items:center; gap:10px; min-height:40px; }
.bar .name { font-size:15px; font-weight:600; }
.bar .scope { font-size:13px; color:var(--muted); }
.dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; vertical-align:1px; background:#8a8a8a; }
.dot.live { background:#2e7d32; } .dot.low { background:#d97706; }
.status { font-size:13px; color:var(--muted); }
.reason { font-size:15px; color:#3d3d3d; margin-top:6px; max-width:760px; }
/* KPI strip */
.summary { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-card); overflow:hidden; }
.kpis { display:grid; grid-template-columns:repeat(5, 1fr); border-top:1px solid var(--border); }
.kpi { padding:14px 18px; border-left:1px solid var(--border); } .kpi:first-child { border-left:0; }
.kpi-label { font-size:13px; font-weight:500; color:var(--muted); }
.kpi-value { font-size:24px; font-weight:400; margin-top:4px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.kpi-value b { font-weight:700; } .unit { font-size:13px; color:var(--muted); font-weight:400; }
/* capacity runway */
.runway { padding:16px 18px 10px; }
.runway .track { position:relative; height:10px; background:#e9ecf1; border-radius:5px; }
.runway .fill { position:absolute; inset:0 auto 0 0; background:var(--hue); border-radius:5px; opacity:.85; }
.runway .mark { position:absolute; top:-5px; width:2px; height:20px; background:var(--negative); transform:translateX(-1px); }
.runway-scale { position:relative; display:flex; justify-content:space-between; font-size:12px; color:var(--muted);
  margin-top:8px; height:16px; font-variant-numeric:tabular-nums; }
.runway-scale .mark-label { position:absolute; transform:translateX(-50%); color:var(--negative); white-space:nowrap; }
/* option cards */
.opts { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.opt { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-card); padding:18px 20px; }
.opt-rec { border:1px solid var(--accent); }
.opt-head { display:flex; justify-content:space-between; align-items:center; }
.opt-name { font-size:16px; font-weight:500; }
.pill { font-size:12px; font-weight:500; background:var(--accent); color:#fff; border-radius:999px; padding:3px 10px; }
.opt-size { font-size:14px; color:var(--muted); margin-top:2px; }
.opt-money { font-size:30px; margin:10px 0 8px; font-variant-numeric:tabular-nums; } .opt-money b { font-weight:700; }
.opt dl { display:grid; grid-template-columns:1fr auto; gap:6px 12px; margin:0; font-size:14px; }
.stApp .opt dt { color:var(--muted); font-weight:400; margin:0; padding:0; }
.stApp .opt dd { margin:0; padding:0; text-align:right; font-variant-numeric:tabular-nums; }
.foot { font-size:13px; color:var(--muted); }
@media (max-width: 760px) {
  .kpis { grid-template-columns:1fr 1fr; } .kpi { border-left:0; border-top:1px solid var(--border); }
  .kpi:nth-child(-n+2) { border-top:0; } .kpi:last-child { grid-column:span 2; } .opts { grid-template-columns:1fr; } .stApp h1 { font-size:24px; }
}
@media (prefers-reduced-motion: reduce) { * { transition:none !important; animation:none !important; } }
</style>
"""

MARK_SVG = ('<svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><path d="M3 15a8 8 0 0 1 16 0" fill="none" '
            'stroke="#141414" stroke-width="2.2" stroke-linecap="round"/><path d="M11 15l4.5-5" stroke="#1d5fbf" '
            'stroke-width="2.2" stroke-linecap="round"/><circle cx="11" cy="15" r="1.8" fill="#141414"/></svg>')


# ---------- rendering ----------
def main():
    import pandas as pd
    import plotly.graph_objects as go
    import streamlit as st

    st.set_page_config(page_title="Capacity Oracle", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    def default_url() -> str:
        if os.environ.get("ORACLE_API_URL"):
            return os.environ["ORACLE_API_URL"]
        # touching st.secrets without a secrets file renders an error box, so check Streamlit's own paths first
        if not any(Path(p).exists() for p in st.get_option("secrets.files")):
            return ""
        try:
            return str(st.secrets.get("ORACLE_API_URL", "") or "")
        except Exception:  # noqa: BLE001 — malformed secrets must not take the dashboard down
            return ""

    # top bar: mark + name + scope on the left; connection and refresh on the right
    brand, conn, refresh = st.columns([6, 1.3, 1], vertical_alignment="center")
    with conn, st.popover("Connection", use_container_width=True):
        offline = st.toggle("Offline mode", value=not default_url(),
                            help="Call the service code directly instead of the API")
        url = st.text_input("API URL", default_url() or "http://localhost:8000", disabled=offline)
    with refresh:
        if st.button("Refresh", use_container_width=True):
            st.cache_data.clear()
    with brand:
        st.markdown(f'<div class="bar">{MARK_SVG}<span class="name">Capacity Oracle</span>'
                    f'<span class="scope">{"demo data" if offline else "ap-south-1 · live API"}</span></div>',
                    unsafe_allow_html=True)

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
            c2, src, quality = get("forecast", base)
            c3, _ = get("plan", base)
    except ApiError as e:
        st.error(f"{e}. Check the URL or turn on Offline mode under Connection.")
        st.stop()

    try:
        actual = pd.DataFrame(get("recent", base, 24))
        actual_err = None
    except ApiError as e:
        actual, actual_err = pd.DataFrame(), e

    # 1. notices, then the title row: the answer is the h1, the reason is its subline
    if offline:
        st.info("Demo data: live API not connected yet")
    if quality["confidence"] == "low":
        st.warning(low_confidence_text(len(actual) if not actual.empty else None))
    dot = "low" if quality["confidence"] == "low" else ("live" if src == "live" else "")
    st.markdown(f'<div class="status"><span class="dot {dot}"></span>'
                f'{"Sample data" if src == "sample" else "Live"} · {age_text(c3.get("generated_at"), now)} · '
                f'{data_age_text(quality["data_age_minutes"])} · {escape(accuracy_text(c2))}</div>',
                unsafe_allow_html=True)
    st.markdown(f"<h1>{escape(headline(c3))}</h1><div class='reason'>{escape(c3.get('reason', ''))}</div>",
                unsafe_allow_html=True)

    # 2. the finding (countdown) and the capacity runway
    text, level = countdown(c2.get("exhaustion_at"), c2.get("cpu_threshold_pct", 70), now)
    {"ok": st.success, "warning": st.warning, "critical": st.error}[level](text)
    st.markdown('<div class="summary">' + runway_html(c2.get("exhaustion_at"), c2.get("horizon_minutes", 1440), now,
                c2.get("cpu_threshold_pct", 70)) + kpi_html(c3) + "</div>", unsafe_allow_html=True)

    # 3. forecast vs actual: forecast in the one hue, actual in ink, one y-axis per chart
    st.subheader("Forecast vs actual")
    if actual_err:
        st.info(f"Actual metrics unavailable: {actual_err}")
    fc = pd.DataFrame(c2["series"])

    def style(fig, height: int, label: str):
        fig.update_layout(height=height, margin={"l": 56, "r": 16, "t": 28, "b": 36}, hovermode="x unified",
                          paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                          font={"family": "Geist, Inter, system-ui, sans-serif", "size": 12, "color": MUTED},
                          legend={"orientation": "h", "y": 1.02, "x": 1, "xanchor": "right", "yanchor": "bottom",
                                  "font": {"color": INK}},
                          yaxis={"title": {"text": label, "standoff": 8}, "gridcolor": GRID, "zeroline": False,
                                 "automargin": True},
                          xaxis={"gridcolor": GRID, "showline": False, "automargin": True})

    def chart(col: str, label: str, band: bool, threshold: float | None = None, height: int = 230):
        fig = go.Figure()
        if band:
            fig.add_trace(go.Scatter(x=list(fc.timestamp) + list(fc.timestamp[::-1]),
                                     y=list(fc.upper) + list(fc.lower[::-1]), fill="toself",
                                     fillcolor=HUE_BAND, line={"width": 0}, name="forecast range", hoverinfo="skip"))
        if not actual.empty:
            fig.add_trace(go.Scatter(x=actual.timestamp, y=actual[col], name="actual",
                                     line={"color": INK, "width": 2}))
        fig.add_trace(go.Scatter(x=fc.timestamp, y=fc[col], name="forecast",
                                 line={"color": HUE, "width": 2, "dash": "dash"}))
        if threshold is not None:
            fig.add_hline(y=threshold, line={"color": "#8a8a8a", "width": 1, "dash": "dash"},
                          annotation_text=f"{threshold:g}% limit", annotation_font_color=MUTED)
        style(fig, height, label)
        with st.container(border=True):
            st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})

    chart("requests_per_min", "requests / min", band=True, height=280)
    cpu_col, mem_col = st.columns(2)
    with cpu_col:
        chart("cpu_pct", "CPU %", band=False, threshold=c2.get("cpu_threshold_pct", 70))
    with mem_col:
        chart("mem_pct", "memory %", band=False, threshold=MEM_LIMIT_PCT)

    # 4. options
    def cards(plan: dict):
        st.markdown('<div class="opts">' + "".join(
            option_card_html(o, o["strategy"] == plan["recommendation"]) for o in plan["options"]) + "</div>",
            unsafe_allow_html=True)

    st.subheader(f"Options for peak {c3['peak_requests_per_min']:,.0f} req/min")
    cards(c3)
    cur = c3["current"]
    st.markdown(f'<div class="foot">Current setup: {cur["instances"]} × {escape(cur["instance_type"])} at '
                f'{_usd(cur["usd_per_hour"], 4)}/h</div>', unsafe_allow_html=True)

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
        st.info("No stored plans yet. Plans appear here after each pipeline run.")
    else:
        h = pd.DataFrame([{"time": p["generated_at"], "peak rpm": p["peak_requests_per_min"],
                           "recommendation": p["recommendation"],
                           "$/day": next(o["usd_per_day"] for o in p["options"]
                                         if o["strategy"] == p["recommendation"])} for p in hist])
        fig = go.Figure(go.Scatter(x=h["time"], y=h["$/day"], mode="lines+markers",
                                   line={"color": HUE, "width": 2}, marker={"size": 8, "color": HUE},
                                   name="recommended $/day"))
        style(fig, 220, "recommended $/day")
        fig.update_layout(showlegend=False)
        with st.container(border=True):
            st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
        st.dataframe(h, hide_index=True, use_container_width=True,
                     column_config={"$/day": st.column_config.NumberColumn(format="%.2f"),
                                    "peak rpm": st.column_config.NumberColumn(format="%d")})


if __name__ == "__main__":
    main()
