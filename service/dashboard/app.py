"""Oracle dashboard (HANDOFF §8 W3). Run: streamlit run service/dashboard/app.py"""
import os
import sys
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import EMBEDDED_BADGE, RECORDED, ApiError, Client, api_alive

# Console palette, light values. Plotly can't read CSS variables, so CSS repaints these exact colours in dark mode.
INK, MUTED, GRID, HUE, HUE_BAND = "#17130f", "#4f4a41", "#ddd9cf", "#0f4fa8", "rgba(15,79,168,0.16)"
BASELINE, LIMIT = "#8a8478", "#5c564c"
ACCURACY_MD = Path(__file__).resolve().parents[2] / "forecasting" / "results" / "accuracy.md"
ACCURACY_MODELS = (("arima", "ARIMA", HUE), ("lstm", "LSTM", INK), ("same-time-yesterday", "Same time yesterday", BASELINE))
ACCURACY_CAPTION = ("Live data covers ~1 h runs, so the live forecast uses the short-history mode; "
                    "24 h accuracy is measured on Wikipedia and Azure traces.")
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


def accuracy_table(path: Path = ACCURACY_MD) -> list[dict]:
    """Main table of accuracy.md as [{dataset, arima, lstm, same-time-yesterday}] (MAPE %); [] if missing or unreadable."""
    if not path.is_file():
        return []
    cols, by_dataset = None, {}
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cols is None:
            if line.startswith("|") and cells[:2] == ["dataset", "model"] and "MAPE %" in cells:
                cols = cells
        elif not line.startswith("|"):
            break
        elif len(cells) == len(cols) and not set(cells[0]) <= {"-"}:
            model = next((m for m, _, _ in ACCURACY_MODELS if cells[1].startswith(m)), None)
            if model:
                try:
                    by_dataset.setdefault(cells[0], {"dataset": cells[0]})[model] = float(cells[cols.index("MAPE %")])
                except ValueError:
                    pass
    return list(by_dataset.values())


def break_gaps(rows: list[dict], max_gap_min: int = 5) -> list[dict]:
    """Insert a blank row wherever rows are over max_gap_min apart, so a line chart doesn't join separate runs."""
    out = []
    for r in rows:
        if out and parse(r["timestamp"]) - parse(out[-1]["timestamp"]) > timedelta(minutes=max_gap_min):
            out.append(dict.fromkeys(r) | {"timestamp": r["timestamp"]})
        out.append(r)
    return out


def replay_text(replay_at: str | None) -> str | None:
    return f"Replay of recorded run ({replay_at[:10]})" if replay_at else None


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


def sparse_note(n_forecast: int, n_actual: int) -> str | None:
    """Honest note for a chart with too few points to draw a line; None when the chart is dense enough."""
    if n_forecast >= 3 or n_actual >= 3:
        return None
    pts = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return (f"This data has {pts(n_forecast, 'forecast point')} and {pts(n_actual, 'metric row')}, "
            "so the chart shows points rather than lines. Live data fills the next 24 h.")


def compare_html(c3: dict) -> str:
    """Subline built from the plan's numbers (planner's own `reason` text is shown as a note elsewhere)."""
    rec = _rec(c3)
    alt = next((o for o in c3["options"] if o is not rec), None)
    spof = "a single point of failure" if rec["single_point_of_failure"] else "no single point of failure"
    if alt is None:
        return f"{_usd(rec['usd_per_day'])}/day · {rec['expected_latency_ms']:,.0f} ms expected latency · {spof}"
    other = "scale up" if alt["strategy"] == "scale_up" else "scale out"
    return (f"{_usd(rec['usd_per_day'])}/day against {_usd(alt['usd_per_day'])}/day to {other} · "
            f"{rec['expected_latency_ms']:,.0f} ms expected latency against {alt['expected_latency_ms']:,.0f} ms · {spof}")


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
    memory = "<dt>Sizing</dt><dd>limited by memory</dd>" if o.get("memory_constrained") else ""  # older plans lack the key
    return (f'<div class="opt{" opt-rec" if recommended else ""}"><div class="opt-head"><span class="opt-name">{name}</span>{tag}</div>'
            f'<div class="opt-size">{o["instances"]} × {escape(o["instance_type"])}</div>'
            f'<div class="opt-money"><b>{_usd(o["usd_per_day"])}</b><span class="unit"> /day</span></div>'
            f'<dl><dt>Hourly</dt><dd>{_usd(o["usd_per_hour"], 3)}</dd>'
            f'<dt>Expected latency</dt><dd>{o["expected_latency_ms"]:,.0f} ms</dd>'
            f'<dt>Single point of failure</dt><dd>{spof}</dd>{memory}</dl></div>')


def delta_text(c3: dict) -> str:
    cur = c3["current"]["usd_per_hour"] * 24
    rec = _rec(c3)
    diff = rec["usd_per_day"] - cur
    return (f"Recommended {rec['strategy'].replace('_', '-')} costs \\${rec['usd_per_day']:.2f}/day, "
            f"{'+' if diff >= 0 else '−'}\\${abs(diff):.2f}/day vs current ({c3['current']['instances']} × "
            f"{c3['current']['instance_type']}).")


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Host+Grotesk:wght@400;500;600'
         '&family=Atkinson+Hyperlegible+Mono:wght@400;500;600&display=swap" rel="stylesheet">')
# st.markdown ends a style block at a blank line, so the stylesheet must stay free of them
CSS = f'{FONTS}<style>{Path(__file__).with_name("style.css").read_text()}</style>'

MARK_SVG = ('<svg class="mark" width="24" height="24" viewBox="0 0 22 22" aria-hidden="true"><path class="m-ink" d="M3 15a8 8 0 0 1 16 0" '
            'stroke-width="2.2" stroke-linecap="round"/><path class="m-cool" d="M11 15l4.5-5" '
            'stroke-width="2.2" stroke-linecap="round"/><circle class="m-dot" cx="11" cy="15" r="1.8"/></svg>')


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

    @st.cache_data(ttl=60, show_spinner=False)
    def alive(url: str) -> bool:
        return api_alive(url)

    # top bar: mark + name + scope on the left; connection and refresh on the right
    brand, conn, refresh = st.columns([6, 1.3, 1], vertical_alignment="center")
    with conn, st.popover("Connection", use_container_width=True):
        offline = st.toggle("Offline mode", value=not alive(default_url()),
                            help="Call the service code directly instead of the API")
        url = st.text_input("API URL", default_url() or "http://localhost:8000", disabled=offline)
    with refresh:
        if st.button("Refresh", use_container_width=True):
            st.cache_data.clear()
    embedded = offline and bool(RECORDED)  # API down or not set: run the same code on the recorded AWS run
    scope = "recorded AWS run, in-process" if embedded else ("demo data" if offline else "ap-south-1 · live API")
    with brand:
        st.markdown(f'<div class="bar">{MARK_SVG}<span class="name">Capacity Oracle</span>'
                    f'<span class="scope">{scope}</span></div>', unsafe_allow_html=True)

    client = Client(None if offline else url, embedded=embedded)

    @st.cache_data(ttl=60, show_spinner=False)
    def get(kind: str, base: str | None, arg=None, emb: bool = False):
        c = Client(base, embedded=emb)
        return {"forecast": c.forecast, "plan": c.plan, "history": c.history, "recent": c.recent}[kind](
            *([] if arg is None else [arg]))

    base = client.base_url
    now = datetime.now(UTC)
    try:
        with st.spinner("Loading forecast and plan…"):
            c2, src, quality = get("forecast", base, None, embedded)
            c3, _ = get("plan", base, None, embedded)
    except ApiError as e:
        st.error(f"{e}. Check the URL or turn on Offline mode under Connection.")
        st.stop()

    try:
        actual = pd.DataFrame(get("recent", base, 24, embedded))
        actual_err = None
    except ApiError as e:
        actual, actual_err = pd.DataFrame(), e

    # 1. notices, then the title row: the answer is the h1, the reason is its subline
    if embedded:
        st.markdown(f'<span class="pill notice">{EMBEDDED_BADGE}</span>', unsafe_allow_html=True)
    elif offline:
        st.info("Demo data: live API not connected yet")
    if quality["confidence"] == "low":
        st.warning(low_confidence_text(len(actual) if not actual.empty else None))
    replay = replay_text(quality.get("replay_at"))
    clock = parse(quality["replay_at"]) if replay else now  # "updated N ago" below stays on the wall clock
    if replay:
        st.markdown(f'<span class="pill notice">{replay}</span>', unsafe_allow_html=True)
    dot = "low" if quality["confidence"] == "low" else ("live" if src == "live" else "")
    st.markdown(f'<div class="status"><span class="dot {dot}"></span>'
                f'{ {"sample": "Sample data", "embedded": "Recorded run"}.get(src, "Live")} · {age_text(c3.get("generated_at"), now)} · '
                f'{data_age_text(quality["data_age_minutes"])} · {escape(accuracy_text(c2))}</div>',
                unsafe_allow_html=True)
    st.markdown(f"<h1>{escape(headline(c3))}</h1><div class='reason'>{compare_html(c3)}</div>",
                unsafe_allow_html=True)

    # 2. the finding (countdown) and the capacity runway
    text, level = countdown(c2.get("exhaustion_at"), c2.get("cpu_threshold_pct", 70), clock)
    {"ok": st.success, "warning": st.warning, "critical": st.error}[level](text)
    st.markdown('<div class="summary">' + runway_html(c2.get("exhaustion_at"), c2.get("horizon_minutes", 1440), clock,
                c2.get("cpu_threshold_pct", 70)) + kpi_html(c3) + "</div>", unsafe_allow_html=True)

    # 3. forecast vs actual: forecast in the one hue, actual in ink, one y-axis per chart
    st.subheader("Forecast vs actual")
    if actual_err:
        st.info(f"Actual metrics unavailable: {actual_err}")
    fc = pd.DataFrame(c2["series"])

    def style(fig, height: int, label: str):
        fig.update_layout(height=height, margin={"l": 56, "r": 16, "t": 28, "b": 36}, hovermode="x unified",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font={"family": "Host Grotesk, system-ui, sans-serif", "size": 14, "color": MUTED},
                          legend={"orientation": "h", "y": 1.02, "x": 1, "xanchor": "right", "yanchor": "bottom",
                                  "font": {"color": INK, "size": 14}},
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
            rows = break_gaps(actual.to_dict("records"))
            fig.add_trace(go.Scatter(x=[r["timestamp"] for r in rows], y=[r[col] for r in rows], name="actual",
                                     mode="lines+markers", marker={"size": 3, "color": INK},  # lone rows stay visible
                                     line={"color": INK, "width": 2.5}))
        few = len(fc) < 3
        fig.add_trace(go.Scatter(x=fc.timestamp, y=fc[col], name="forecast", mode="lines+markers" if few else "lines",
                                 line={"color": HUE, "width": 3, "dash": "dash"}, marker={"size": 9, "color": HUE}))
        if threshold is not None:
            fig.add_hline(y=threshold, line={"color": LIMIT, "width": 1.5, "dash": "dash"},
                          annotation_text=f"{threshold:g}% limit", annotation_font_color=MUTED)
        style(fig, height, label)
        with st.container(border=True):
            st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
            if note:
                st.caption(note)

    note = sparse_note(len(fc), len(actual))
    chart("requests_per_min", "requests / min", band=True, height=280)
    cpu_col, mem_col = st.columns(2)
    with cpu_col:
        chart("cpu_pct", "CPU %", band=False, threshold=c2.get("cpu_threshold_pct", 70))
    with mem_col:
        chart("mem_pct", "memory %", band=False, threshold=MEM_LIMIT_PCT)

    # model accuracy: offline results from Member 2, hidden until the file exists
    accuracy = accuracy_table()
    if accuracy:
        st.subheader("Model accuracy (offline evaluation)")
        with st.container(border=True):
            fig = go.Figure([go.Bar(x=[r["dataset"] for r in accuracy], y=[r.get(key) for r in accuracy], name=name,
                                    marker_color=color) for key, name, color in ACCURACY_MODELS])
            fig.update_layout(barmode="group")
            style(fig, 260, "MAPE % (lower is better)")
            st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
            st.dataframe(pd.DataFrame([{"Dataset": r["dataset"], **{name: f"{r[key]:.2f}" if key in r else "—" for key, name, _ in ACCURACY_MODELS}}
                                       for r in accuracy]), hide_index=True, use_container_width=True)
            st.caption(ACCURACY_CAPTION)

    # 4. options
    def cards(plan: dict):
        st.markdown('<div class="opts">' + "".join(
            option_card_html(o, o["strategy"] == plan["recommendation"]) for o in plan["options"]) + "</div>",
            unsafe_allow_html=True)

    st.subheader(f"Options for peak {c3['peak_requests_per_min']:,.0f} req/min")
    cards(c3)
    cur = c3["current"]
    note = f' · Planner note: {escape(c3["reason"])}' if c3.get("reason") else ""
    st.markdown(f'<div class="foot">Current setup: {cur["instances"]} × {escape(cur["instance_type"])} at '
                f'{_usd(cur["usd_per_hour"], 4)}/h{note.replace("$", "&#36;")}</div>', unsafe_allow_html=True)

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
        hist = get("history", base, 7, embedded)
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
