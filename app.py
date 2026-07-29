"""
app.py
-------
Entry point for the Warehouse Operations Intelligence Dashboard.

Run with:  streamlit run app.py
"""
import json
import numpy as np
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from streamlit_autorefresh import st_autorefresh
from streamlit.components.v1 import html as st_html

from modules.auth import AuthManager
from modules.data_loader import DataLoader, resolve_columns
from modules.filters import render_sidebar_filters
from modules.export import render_export_buttons
from modules import charts as C
from modules.manager_reports import fetch_manager_sheet, test_manager_connection

# ----------------------------------------------------------------------------
# PAGE CONFIG + CONFIG LOAD
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Ops Intelligence Dashboard", page_icon="📦",
                    layout="wide", initial_sidebar_state="expanded")

with open("config.json", "r", encoding="utf-8") as f:
    CFG = json.load(f)
COLS = CFG["columns"]

TAB_TITLES = [
    "🏆 Executive", "📅 Daily Performance", "👤 Team Leader", "🏷️ Activity",
    "📍 Location", "⚡ Productivity", "🎯 Planned vs Achieved", "👷 Manpower",
    "⏱️ Time Analysis", "📈 Monthly Trend", "🥇 Leaderboard", "🔬 Analytics",
    "🧭 Management", "📋 Reports / Data",
]
SLIDE_SECONDS = 15

# ----------------------------------------------------------------------------
# GLOBAL STYLE (glassmorphism, gradients, dark/light, animations)
# ----------------------------------------------------------------------------
def inject_css(dark: bool, kiosk: bool = False):
    bg = "#0E1117" if dark else "#F3F4F6"
    card_bg = "rgba(255,255,255,0.06)" if dark else "rgba(255,255,255,0.85)"
    text = "#F9FAFB" if dark else "#111827"
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] {{ font-family:'Inter', sans-serif; }}
    .stApp {{ background:{bg}; color:{text}; }}

    .kpi-card {{
        border-radius:18px; padding:18px 16px; color:white; position:relative;
        box-shadow:0 8px 24px rgba(0,0,0,0.25); transition:transform .25s ease, box-shadow .25s ease;
        overflow:hidden; min-height:128px;
    }}
    .kpi-card:hover {{ transform:translateY(-6px) scale(1.02); box-shadow:0 14px 32px rgba(0,0,0,0.35); }}
    .kpi-icon {{ font-size:22px; opacity:.9; }}
    .kpi-value {{ font-size:28px; font-weight:800; margin-top:6px; }}
    .kpi-label {{ font-size:13px; opacity:.92; font-weight:600; margin-top:2px; }}
    .kpi-sub {{ font-size:11px; opacity:.8; margin-top:4px; }}

    .glass-panel {{
        background:{card_bg}; backdrop-filter: blur(10px);
        border-radius:18px; padding:16px 18px; border:1px solid rgba(255,255,255,0.10);
        margin-bottom:14px;
    }}
    .section-title {{
        font-size:20px; font-weight:800; margin:18px 0 8px 0;
        background:linear-gradient(90deg,#7C3AED,#06B6D4);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 6px; flex-wrap: wrap; }}
    .stTabs [data-baseweb="tab"] {{
        border-radius:10px 10px 0 0; padding:8px 14px; font-weight:600;
    }}
    section[data-testid="stSidebar"] {{ border-right:1px solid rgba(255,255,255,0.08); }}
    .live-banner {{
        display:inline-block; padding:6px 18px; border-radius:20px;
        background:linear-gradient(90deg,#EF4444,#F59E0B); color:white;
        font-weight:800; font-size:clamp(18px, 1.5vw, 23px); letter-spacing:1px; margin-right:14px;
        animation: pulse 1.4s infinite; vertical-align:middle;
    }}
    @keyframes pulse {{ 0%{{opacity:1}} 50%{{opacity:.55}} 100%{{opacity:1}} }}
    .slide-param-name {{
        font-size:clamp(16px, 1.3vw, 21px); font-weight:800; margin:8px 0 4px 0; line-height:1.15;
        color:{text};
    }}
    .slide-manager-name {{
        font-size:clamp(23px, 2.6vw, 38px); font-weight:800; opacity:.92; margin-bottom:2px;
        vertical-align:middle;
    }}
    .app-title {{
        font-size:clamp(24px, 2.4vw, 38px); font-weight:800; margin:0; line-height:1.2;
    }}
    .active-source-line {{
        font-size:clamp(15px, 1.2vw, 19px); font-weight:600; margin-top:2px;
    }}
    </style>
    """, unsafe_allow_html=True)

    if kiosk:
        # FULL-SCREEN KIOSK MODE: hide the sidebar entirely, hide Streamlit's
        # own chrome (hamburger menu, footer, header bar), and reclaim the
        # padding those normally take up, so the slideshow uses the whole
        # screen — meant for a TV/wall display, not day-to-day filtering.
        # Also tighten card/heading spacing so the auto-fit script (which
        # scales the page down only as much as needed to avoid scrolling)
        # has less excess whitespace to remove, keeping text as large and
        # readable as possible.
        st.markdown("""
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header[data-testid="stHeader"] { visibility: hidden; height: 0; }
        .block-container { padding-top: 0.8rem; padding-bottom: 0.5rem; max-width: 100% !important; }
        .kpi-card { min-height: 92px; padding: 12px 14px; }
        .kpi-value { font-size: 24px; margin-top: 3px; }
        .section-title { margin: 10px 0 6px 0; font-size: 17px; }
        div[data-testid="stVerticalBlock"] > div { gap: 0.4rem; }
        </style>
        """, unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# CONTEXT BUILDER — turns any cleaned dataframe (the main dataset, filtered
# or not, or a manager's sheet) into everything the 14 tabs need. Used by
# BOTH the normal tabbed view and the Live Slideshow, so every KPI/chart
# formula lives in exactly one place.
# ----------------------------------------------------------------------------
def build_context(fdf: pd.DataFrame, cfg: dict) -> dict:
    c = cfg["columns"]

    total_planned_qty   = fdf[c["planned_qty"]].sum()
    total_achieved_qty  = fdf[c["achieved_qty"]].sum()
    achievement_pct     = (total_achieved_qty / total_planned_qty * 100) if total_planned_qty else 0
    total_planned_mp    = fdf[c["planned_total_mp"]].sum()
    total_achieved_mp   = fdf[c["achieved_total_mp"]].sum()
    mp_eff              = (total_achieved_mp / total_planned_mp * 100) if total_planned_mp else 0
    avg_time_eff        = fdf["Time_Efficiency_%"].mean()
    n_tl                = fdf[c["team_leader"]].nunique()
    n_activities        = fdf[c["activity"]].nunique()
    n_locations         = fdf[c["location"]].nunique()

    # PPPM Achievement Rate = (Avg Achieved PPPM / Avg Planned PPPM) x 100
    avg_planned_pppm  = pd.to_numeric(fdf[c["planned_pppm"]],  errors="coerce").mean()
    avg_achieved_pppm = pd.to_numeric(fdf[c["achieved_pppm"]], errors="coerce").mean()
    pppm_rate = (avg_achieved_pppm / avg_planned_pppm * 100) if (avg_planned_pppm and avg_planned_pppm != 0) else 0

    daily = fdf.groupby("DateOnly").agg(
        Planned_Qty=(c["planned_qty"],       "sum"),
        Achieved_Qty=(c["achieved_qty"],     "sum"),
        Planned_MP=(c["planned_total_mp"],   "sum"),
        Achieved_MP=(c["achieved_total_mp"], "sum"),
    ).reset_index()
    daily["Achievement_%"] = (daily["Achieved_Qty"] / daily["Planned_Qty"].replace(0, np.nan) * 100)

    by_tl = fdf.groupby(c["team_leader"]).agg(
        Planned_Qty=(c["planned_qty"],       "sum"),
        Achieved_Qty=(c["achieved_qty"],     "sum"),
        Planned_MP=(c["planned_total_mp"],   "sum"),
        Achieved_MP=(c["achieved_total_mp"], "sum"),
        Records=(c["activity"],              "count"),
    ).reset_index()
    by_tl["Achievement_%"] = (by_tl["Achieved_Qty"] / by_tl["Planned_Qty"].replace(0, np.nan) * 100).round(1)
    by_tl = by_tl.sort_values("Achievement_%", ascending=False)

    by_activity = fdf.groupby(c["activity"]).agg(
        Planned_Qty=(c["planned_qty"],   "sum"),
        Achieved_Qty=(c["achieved_qty"], "sum"),
        Records=(c["activity"],          "count"),
    ).reset_index()
    by_activity["Achievement_%"] = (by_activity["Achieved_Qty"] / by_activity["Planned_Qty"].replace(0, np.nan) * 100).round(1)

    by_location = fdf.groupby(c["location"]).agg(
        Planned_Qty=(c["planned_qty"],   "sum"),
        Achieved_Qty=(c["achieved_qty"], "sum"),
        Records=(c["location"],          "count"),
    ).reset_index()

    by_month = fdf.groupby("MonthName").agg(
        Planned_Qty=(c["planned_qty"],       "sum"),
        Achieved_Qty=(c["achieved_qty"],     "sum"),
        Planned_MP=(c["planned_total_mp"],   "sum"),
        Achieved_MP=(c["achieved_total_mp"], "sum"),
    ).reset_index()
    by_month["_order"] = pd.to_datetime(by_month["MonthName"], format="%b %Y")
    by_month = by_month.sort_values("_order")

    return dict(
        fdf=fdf, c=c,
        total_planned_qty=total_planned_qty, total_achieved_qty=total_achieved_qty,
        achievement_pct=achievement_pct, total_planned_mp=total_planned_mp,
        total_achieved_mp=total_achieved_mp, mp_eff=mp_eff, avg_time_eff=avg_time_eff,
        n_tl=n_tl, n_activities=n_activities, n_locations=n_locations,
        avg_planned_pppm=avg_planned_pppm, avg_achieved_pppm=avg_achieved_pppm, pppm_rate=pppm_rate,
        daily=daily, by_tl=by_tl, by_activity=by_activity, by_location=by_location, by_month=by_month,
    )


def render_kpi_header(ctx: dict) -> None:
    st.markdown('<div class="section-title">📊 Executive KPI Overview</div>', unsafe_allow_html=True)
    k = st.columns(3)
    with k[0]:
        C.kpi_card("Total Records", f"{len(ctx['fdf']):,}", "Filtered rows", "🧾", ("#7C3AED", "#A78BFA"))
    with k[1]:
        C.kpi_card("PPPM Achievement Rate", f"{ctx['pppm_rate']:,.1f}%",
                    f"Planned {ctx['avg_planned_pppm']:,.1f}  vs  Achieved {ctx['avg_achieved_pppm']:,.1f}",
                    "📊", ("#10B981", "#34D399"))
    with k[2]:
        C.kpi_card("Avg Time Efficiency", f"{ctx['avg_time_eff']:,.1f}%",
                    ">100% = team finishing faster than planned", "⏱️", ("#F59E0B", "#FBBF24"))
    st.markdown("")


def render_tab_content(idx: int, ctx: dict, compact: bool = False, extra_room: bool = False) -> None:
    """Renders the body of ONE tab (0-13), using pre-computed values from
    build_context(). Called both inside the normal st.tabs() widget AND,
    standalone (one index at a time), by the Live Slideshow — so the exact
    same chart code and formulas power both views with zero duplication.

    compact=True (used only by the slideshow) requests genuinely smaller
    chart heights so a slide's full content fits on one screen with no
    scrolling — real Plotly height values, not a CSS zoom/scale trick.

    extra_room=True (slideshow only, on tabs where the KPI header is
    skipped — see render_slideshow) bumps those compact heights back up a
    bit, since skipping the KPI header frees up real vertical space that
    would otherwise sit blank."""
    fdf = ctx["fdf"]; c = ctx["c"]
    daily = ctx["daily"]; by_tl = ctx["by_tl"]; by_activity = ctx["by_activity"]
    by_location = ctx["by_location"]; by_month = ctx["by_month"]
    total_planned_qty = ctx["total_planned_qty"]; total_achieved_qty = ctx["total_achieved_qty"]
    achievement_pct = ctx["achievement_pct"]; total_planned_mp = ctx["total_planned_mp"]
    total_achieved_mp = ctx["total_achieved_mp"]; mp_eff = ctx["mp_eff"]; avg_time_eff = ctx["avg_time_eff"]

    bump = 55 if (compact and extra_room) else 0
    H   = (205 + bump) if compact else 420   # generic line/area/bar/donut/pie/scatter chart
    HG  = (175 + round(bump * 0.7)) if compact else 320   # gauge
    HP  = (H + 50) if compact else 440   # pie/donut/sunburst — these are circular, so
                                           # they need real height (not just width) to
                                           # actually look sized-up; a wide-but-short box
                                           # just leaves the circle small with blank space
                                           # on either side. Kept modest (+50, tried +140
                                           # then +70 first) because a taller pie/donut
                                           # also makes its ROW taller (Streamlit sizes a
                                           # row to its tallest chart) — too big and it
                                           # pushes later content off the bottom of the
                                           # screen. Tabs with TWO stacked circular charts
                                           # (e.g. Activity: pie + sunburst) compound this,
                                           # so the per-chart bump has to stay conservative.
    HSK = (250 + bump) if compact else 520   # sankey (needs a bit more room for labels)
    HWF = (205 + bump) if compact else 420   # waterfall
    DF_H = (190 + bump) if compact else None # dataframe height (None = Streamlit's own default)

    # ---- 1. EXECUTIVE ----
    if idx == 0:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(C.line_chart(daily, "DateOnly", ["Planned_Qty", "Achieved_Qty"],
                                         title="Daily Planned vs Achieved Qty", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.donut_chart(by_activity, c["activity"], "Achieved_Qty",
                                          title="Achieved Qty Share by Activity", height=HP), use_container_width=True)
        col3, col4 = st.columns(2)
        with col3:
            st.plotly_chart(C.gauge_chart(achievement_pct, "Overall Achievement %", height=HG), use_container_width=True)
        with col4:
            st.plotly_chart(C.gauge_chart(mp_eff, "Manpower Efficiency %", height=HG), use_container_width=True)
        if not compact:
            # Skipped in the slideshow: with 4 charts already above, a 5th
            # (this treemap) reliably pushed slides taller than any screen.
            try:
                st.plotly_chart(C.treemap_chart(fdf, [c["category"], c["activity"]], c["achieved_qty"],
                                                 title="Achieved Qty Treemap — Category → Activity"), use_container_width=True)
            except Exception as e:
                st.warning(f"⚠️ Treemap could not render: {e}")

    # ---- 2. DAILY PERFORMANCE ----
    elif idx == 1:
        st.plotly_chart(C.area_chart(daily, "DateOnly", ["Planned_Qty", "Achieved_Qty"],
                                      title="Daily Volume Trend (Area)", height=H), use_container_width=True)
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(C.bar_chart(daily, "DateOnly", "Achievement_%",
                                         title="Daily Achievement %", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.line_chart(daily, "DateOnly", ["Planned_MP", "Achieved_MP"],
                                          title="Daily Manpower: Plan vs Actual", height=H), use_container_width=True)

    # ---- 3. TEAM LEADER ----
    elif idx == 2:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(C.bar_chart(by_tl.head(15), c["team_leader"], "Achievement_%",
                                         title="Top 15 TLs by Achievement %", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.bar_chart(by_tl.sort_values("Records", ascending=False).head(15),
                                         c["team_leader"], "Records",
                                         title="Top 15 TLs by Activity Volume", height=H), use_container_width=True)
        if not compact:
            st.plotly_chart(C.radar_chart(
                by_tl.head(6)[c["team_leader"]].tolist(),
                {"Achievement %": by_tl.head(6)["Achievement_%"].fillna(0).round(1).tolist()},
                title="Top 6 TL Achievement Radar"), use_container_width=True)
            st.dataframe(by_tl, use_container_width=True, hide_index=True)
        else:
            st.dataframe(by_tl.head(8), use_container_width=True, hide_index=True, height=DF_H)

    # ---- 4. ACTIVITY ----
    elif idx == 3:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(C.bar_chart(by_activity.sort_values("Achieved_Qty", ascending=False),
                                         c["activity"], "Achieved_Qty",
                                         title="Achieved Qty by Activity", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.pie_chart(by_activity, c["activity"], "Records",
                                         title="Activity Record Share", height=HP), use_container_width=True)
        if not compact or extra_room:
            st.plotly_chart(C.sunburst_chart(fdf, [c["category"], c["activity"], c["location"]], c["achieved_qty"],
                                              title="Category → Activity → Location Sunburst",
                                              height=(HP if compact else 500)), use_container_width=True)

    # ---- 5. LOCATION ----
    elif idx == 4:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(C.bar_chart(by_location.sort_values("Achieved_Qty", ascending=False),
                                         c["location"], "Achieved_Qty",
                                         title="Achieved Qty by Location", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.donut_chart(by_location, c["location"], "Records",
                                           title="Record Share by Location", height=HP), use_container_width=True)
        if not compact or extra_room:
            st.plotly_chart(C.heatmap_chart(fdf, c["location"], c["activity"], "Achievement_%",
                                             title="Heatmap: Activity × Location Achievement %",
                                             height=(H if compact else 460)), use_container_width=True)

    # ---- 6. PRODUCTIVITY ----
    elif idx == 5:
        col1, col2 = st.columns(2)
        with col1:
            prod = fdf.groupby(c["team_leader"])[[c["planned_pppm"], c["achieved_pppm"]]].mean(numeric_only=True).reset_index()
            st.plotly_chart(C.bar_chart(prod.head(20), c["team_leader"], [c["planned_pppm"], c["achieved_pppm"]],
                                         title="Avg PPPM (Planned vs Achieved) by TL", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.scatter_chart(fdf, c["planned_qty"], c["achieved_qty"], color=c["activity"],
                                             title="Planned vs Achieved Qty (per record)", height=H), use_container_width=True)
        if not compact or extra_room:
            st.plotly_chart(C.bubble_chart(by_tl, "Planned_MP", "Achieved_MP", "Records", color=c["team_leader"],
                                            title="TL Bubble: Planned MP vs Achieved MP (size=Records)",
                                            height=(H if compact else 500)), use_container_width=True)

    # ---- 7. PLANNED VS ACHIEVED ----
    elif idx == 6:
        pva = pd.DataFrame({
            "Metric":   ["Qty",              "Manpower"],
            "Planned":  [total_planned_qty,  total_planned_mp],
            "Achieved": [total_achieved_qty, total_achieved_mp],
        })
        if compact:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(C.bar_chart(pva, "Metric", ["Planned", "Achieved"],
                                             title="Overall Planned vs Achieved", height=H), use_container_width=True)
            with col2:
                st.plotly_chart(C.waterfall_chart(["Planned Qty", "Variance"],
                                                   [total_planned_qty, total_achieved_qty - total_planned_qty],
                                                   title="Qty Variance Waterfall", measure=["absolute", "relative"],
                                                   height=HWF), use_container_width=True)
        else:
            st.plotly_chart(C.bar_chart(pva, "Metric", ["Planned", "Achieved"],
                                         title="Overall Planned vs Achieved"), use_container_width=True)
            st.plotly_chart(C.waterfall_chart(["Planned Qty", "Variance"],
                                               [total_planned_qty, total_achieved_qty - total_planned_qty],
                                               title="Qty Variance Waterfall", measure=["absolute", "relative"]),
                             use_container_width=True)
        if not compact or extra_room:
            st.plotly_chart(C.bar_chart(by_activity, c["activity"], ["Planned_Qty", "Achieved_Qty"],
                                         title="Planned vs Achieved Qty by Activity",
                                         height=(H if compact else 440)), use_container_width=True)

    # ---- 8. MANPOWER ----
    elif idx == 7:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(C.bar_chart(by_tl, c["team_leader"], ["Planned_MP", "Achieved_MP"],
                                         title="Manpower: Planned vs Achieved by TL", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.donut_chart(fdf, c["team_leader"], c["achieved_total_mp"],
                                           title="Achieved Manpower Share by TL", height=HP), use_container_width=True)
        if not compact or extra_room:
            mp_eff_dist = fdf[["MP_Efficiency_%"]].dropna()
            st.plotly_chart(px.histogram(mp_eff_dist, x="MP_Efficiency_%", nbins=30,
                                          title="Manpower Efficiency Distribution", height=(H if compact else None))
                             .update_layout(template="plotly_dark" if st.session_state.dark_mode else "plotly_white"),
                             use_container_width=True)

    # ---- 9. TIME ANALYSIS ----
    elif idx == 8:
        col1, col2 = st.columns(2)
        with col1:
            time_by_act = fdf.groupby(c["activity"])[[c["planned_time"], c["achieved_time"]]].mean(numeric_only=True).reset_index()
            st.plotly_chart(C.bar_chart(time_by_act, c["activity"], [c["planned_time"], c["achieved_time"]],
                                         title="Avg Time (min): Planned vs Achieved by Activity", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.gauge_chart(avg_time_eff, "Avg Time Efficiency %", max_value=200, height=HG), use_container_width=True)
        if not compact or extra_room:
            st.plotly_chart(C.line_chart(
                daily.assign(**{"Time_Eff": (daily["Achieved_MP"] / daily["Planned_MP"].replace(0, np.nan) * 100)}),
                "DateOnly", "Time_Eff", title="Daily Efficiency Trend",
                height=(H if compact else 420)), use_container_width=True)

    # ---- 10. MONTHLY TREND ----
    elif idx == 9:
        st.plotly_chart(C.line_chart(by_month, "MonthName", ["Planned_Qty", "Achieved_Qty"],
                                      title="Monthly Qty Trend", height=H), use_container_width=True)
        st.plotly_chart(C.area_chart(by_month, "MonthName", ["Planned_MP", "Achieved_MP"],
                                      title="Monthly Manpower Trend", height=H), use_container_width=True)

    # ---- 11. LEADERBOARD ----
    elif idx == 10:
        st.markdown("#### 🥇 Team Leader Leaderboard")
        lb = by_tl.copy()
        lb["Rank"] = range(1, len(lb) + 1)
        lb = lb[["Rank", c["team_leader"], "Achievement_%", "Records", "Achieved_Qty", "Achieved_MP"]]
        if compact:
            st.dataframe(lb.head(8), use_container_width=True, hide_index=True, height=DF_H)
        else:
            st.dataframe(lb, use_container_width=True, hide_index=True)
        st.plotly_chart(C.bar_chart(lb.head(10), c["team_leader"], "Achievement_%",
                                     title="Top 10 Leaderboard", height=H), use_container_width=True)

    # ---- 12. ANALYTICS ----
    elif idx == 11:
        col1, col2 = st.columns(2)
        with col1:
            corr_df = fdf[[c["planned_qty"], c["achieved_qty"], c["planned_total_mp"], c["achieved_total_mp"],
                            "Achievement_%", "MP_Efficiency_%"]].corr()
            st.plotly_chart(C.heatmap_chart(corr_df.reset_index().melt(id_vars="index"),
                                             "variable", "index", "value",
                                             title="Correlation Heatmap", height=H), use_container_width=True)
        with col2:
            st.plotly_chart(C.scatter_chart(fdf, c["achieved_total_mp"], c["achieved_qty"],
                                             color=c["category"], size=c["achieved_qty"],
                                             title="MP vs Qty Achieved (by Category)", height=H), use_container_width=True)
        if not compact or extra_room:
            status_counts = fdf["Status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            st.plotly_chart(C.pie_chart(status_counts, "Status", "Count",
                                         title="Status Distribution",
                                         height=(HP if compact else 420)), use_container_width=True)

    # ---- 13. MANAGEMENT ----
    elif idx == 12:
        st.markdown("#### 🧭 Management Summary")
        m1, m2, m3, m4 = st.columns(4)
        with m1: C.kpi_card("Total Planned Qty",  f"{total_planned_qty:,.0f}",  icon="📦")
        with m2: C.kpi_card("Total Achieved Qty", f"{total_achieved_qty:,.0f}", icon="✅", gradient=("#10B981", "#34D399"))
        with m3: C.kpi_card("Total Planned MP",   f"{total_planned_mp:,.0f}",   icon="👷", gradient=("#06B6D4", "#22D3EE"))
        with m4: C.kpi_card("Total Achieved MP",  f"{total_achieved_mp:,.0f}",  icon="🛠️", gradient=("#F59E0B", "#FBBF24"))
        nodes = list(pd.unique(
            pd.concat([fdf[c["category"]], fdf[c["activity"]], fdf["Status"]]).reset_index(drop=True)
        ))
        idx_map = {n: i for i, n in enumerate(nodes)}
        link1 = fdf.groupby([c["category"], c["activity"]]).size().reset_index(name="v")
        link2 = fdf.groupby([c["activity"], "Status"]).size().reset_index(name="v")
        src = link1[c["category"]].map(idx_map).tolist() + link2[c["activity"]].map(idx_map).tolist()
        tgt = link1[c["activity"]].map(idx_map).tolist() + link2["Status"].map(idx_map).tolist()
        val = link1["v"].tolist() + link2["v"].tolist()
        st.plotly_chart(C.sankey_chart(nodes, src, tgt, val,
                                        title="Flow: Category → Activity → Status", height=HSK), use_container_width=True)

    # ---- 14. REPORTS / DATA ----
    elif idx == 13:
        if compact:
            # Search/pagination/export controls don't make sense in a
            # passive, auto-cycling slideshow — show a compact read-only
            # preview instead of the full interactive tool.
            st.markdown("#### 📋 Filtered Data (preview)")
            table_df = fdf.drop(columns=["DateOnly"], errors="ignore")
            st.dataframe(table_df.head(10), use_container_width=True, hide_index=True, height=DF_H)
            st.caption(f"Showing 10 of {len(table_df):,} records · full search, sort, and export "
                       f"available in the regular dashboard view")
        else:
            st.markdown("#### 📋 Filtered Data — Search, Sort, Paginate, Export")
            search = st.text_input("🔎 Search across all columns", key=f"search_{idx}")
            table_df = fdf.drop(columns=["DateOnly"], errors="ignore")
            if search:
                mask = table_df.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
                table_df = table_df[mask]
            page_size   = st.selectbox("Rows per page", [25, 50, 100, 250], index=1, key=f"page_size_{idx}")
            total_pages = max(1, (len(table_df) - 1) // page_size + 1)
            page        = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key=f"page_{idx}")
            start, end  = (page - 1) * page_size, (page - 1) * page_size + page_size
            st.dataframe(table_df.iloc[start:end], use_container_width=True, hide_index=True)
            st.caption(f"Showing {min(start+1, len(table_df))}-{min(end, len(table_df))} of {len(table_df):,} records")
            render_export_buttons(table_df, "operations_report")


# ----------------------------------------------------------------------------
# LIVE SLIDESHOW — auto-cycles through every data source (the main dataset
# + every configured manager) across all 14 tabs, 15 seconds per slide,
# looping forever. Read-only: fetching a manager's sheet here does NOT
# overwrite the active dataset or touch current_data.xlsx.
# ----------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner="Fetching manager data for slideshow...")
def _load_manager_df_for_slideshow(sheet_url: str, cols_config: dict) -> pd.DataFrame:
    raw = fetch_manager_sheet(sheet_url)
    return resolve_columns(raw, cols_config)


def _slideshow_sources(cfg: dict) -> list:
    sources = [{"kind": "current", "name": None, "sheet_url": None}]
    for m in cfg.get("manager_reports", []):
        sources.append({"kind": "manager", "name": m["name"], "sheet_url": m["sheet_url"]})
    return sources


def _get_source_df(source: dict, loader: DataLoader, main_df: pd.DataFrame, cfg: dict):
    """Returns (dataframe_or_None, display_label, error_or_None)."""
    if source["kind"] == "current":
        label = (loader.get_active_source() or {}).get("name") or cfg["app_name"]
        return main_df, label, None
    try:
        resolved = _load_manager_df_for_slideshow(source["sheet_url"], cfg["columns"])
        clean = loader.transform(resolved)
        return clean, source["name"], None
    except Exception as e:
        return None, source["name"], e


def render_fullscreen_control() -> None:
    """A real 'Enter Full Screen' button using the browser's native
    Fullscreen API — this hides the browser's own tab bar/address bar too,
    not just our page content. Pressing Esc is handled entirely by the
    browser (built into the Fullscreen API, exactly like PowerPoint), and
    we also listen for that exit to automatically click our own
    'Exit Slideshow' button, so leaving full screen also ends the
    slideshow rather than leaving it running windowed."""
    st_html("""
    <div style="text-align:right; margin-bottom:2px;">
      <button id="fs-btn" style="
          background:linear-gradient(90deg,#7C3AED,#06B6D4); color:white; border:none;
          padding:8px 18px; border-radius:8px; font-weight:700; font-size:13px;
          cursor:pointer; font-family:Inter,sans-serif;">
        ⛶ Enter Full Screen (Esc to exit)
      </button>
    </div>
    <script>
      (function() {
        var btn = document.getElementById('fs-btn');
        var doc = window.parent.document;

        function updateLabel() {
          btn.innerText = doc.fullscreenElement
            ? '⛶ Exit Full Screen (Esc)'
            : '⛶ Enter Full Screen (Esc to exit)';
        }

        btn.addEventListener('click', function() {
          if (!doc.fullscreenElement) {
            var el = doc.documentElement;
            var req = el.requestFullscreen || el.webkitRequestFullscreen;
            if (req) { req.call(el).catch(function(){}); }
          } else if (doc.exitFullscreen) {
            doc.exitFullscreen();
          }
        });

        doc.addEventListener('fullscreenchange', function() {
          updateLabel();
          if (!doc.fullscreenElement) {
            // Esc (or any other exit) leaves full screen -> also end the
            // slideshow, mirroring how Esc ends a PowerPoint presentation.
            var btns = doc.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
              if (btns[i].innerText && btns[i].innerText.indexOf('Exit Slideshow') !== -1) {
                btns[i].click();
                break;
              }
            }
          }
        });
      })();
    </script>
    """, height=44)


def render_slideshow(loader: DataLoader, main_df: pd.DataFrame, cfg: dict) -> None:
    sources = _slideshow_sources(cfg)
    n_sources, n_tabs = len(sources), len(TAB_TITLES)
    total_slides = n_sources * n_tabs

    tick = st_autorefresh(interval=SLIDE_SECONDS * 1000, key="slideshow_autorefresh")
    slide_num = tick % total_slides
    src_idx, tab_idx = divmod(slide_num, n_tabs)
    source = sources[src_idx]

    df, label, err = _get_source_df(source, loader, main_df, cfg)

    render_fullscreen_control()

    bar_l, bar_r = st.columns([5, 1])
    with bar_l:
        st.markdown(
            f'<span class="live-banner">● LIVE</span>'
            f'<span class="slide-manager-name">{label}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="slide-param-name">{TAB_TITLES[tab_idx]}</div>', unsafe_allow_html=True)
        st.caption(f"Slide {slide_num + 1} of {total_slides}  ·  {n_sources} sources × {n_tabs} tabs  "
                   f"·  advancing every {SLIDE_SECONDS}s")
    with bar_r:
        if st.button("⏹️ Exit Slideshow", use_container_width=True):
            st.session_state.slideshow_on = False
            st.rerun()

    if err is not None:
        st.error(f"⚠️ Could not load **{label}**: {err}")
        return
    if df is None or df.empty:
        st.warning(f"No data available for **{label}**.")
        return

    ctx = build_context(df, cfg)
    if tab_idx == 0:
        # Only the first tab of each source gets the KPI overview — showing
        # it on all 14 would mean re-displaying the same 3 numbers on every
        # slide for 15s x 14 in a row. Skipping it elsewhere frees real
        # vertical space, which render_tab_content uses for bigger charts
        # (extra_room=True below) instead of leaving it blank.
        render_kpi_header(ctx)
    render_tab_content(tab_idx, ctx, compact=True, extra_room=(tab_idx != 0))


# ----------------------------------------------------------------------------
# AUTH
# ----------------------------------------------------------------------------
auth = AuthManager(CFG["users"])
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True
if "slideshow_on" not in st.session_state:
    # Support auto-starting the slideshow via URL, e.g.
    #   https://your-dashboard-url/?slideshow=1
    # Handy for kiosk/TV setups: bookmark or hard-code that URL on the
    # device and it launches straight into the rotating display after
    # login, with no toggle click needed. (Full screen itself still needs
    # one manual tap on first launch — browsers require a real click
    # before allowing the Fullscreen API, this can't be done from a URL.)
    st.session_state.slideshow_on = st.query_params.get("slideshow") in ("1", "true", "yes")
# kiosk=True hides the sidebar + Streamlit chrome for a true full-screen
# display. Read BEFORE the toggle widget below so there's zero lag between
# clicking the toggle and the layout actually going full-screen.
inject_css(st.session_state.dark_mode, kiosk=st.session_state.slideshow_on)

if not auth.is_logged_in():
    auth.login_screen()
    st.stop()

username, role = auth.current_user()
loader = DataLoader(CFG)
active_source = loader.get_active_source()

# If Live Slideshow is active, skip the normal top bar / admin panel
# entirely and go straight to the full-screen slideshow. Previously the
# normal top bar's "Currently viewing: X" (the persisted admin-selected
# source) rendered ABOVE the slideshow's own "● LIVE — Y" banner (the
# source currently on screen) at the same time — two different, constantly
# out-of-sync labels stacked on one page. Skipping the top bar removes the
# duplication and also reclaims that vertical space for charts.
if st.session_state.slideshow_on:
    try:
        main_df = loader.load()
    except Exception as e:
        st.error(f"Could not load main data file: {e}")
        st.stop()
    render_slideshow(loader, main_df, CFG)
    st.stop()

# ----------------------------------------------------------------------------
# TOP BAR (normal mode only)
# ----------------------------------------------------------------------------
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"

top_logo, top_l, top_r = st.columns([0.7, 3.3, 1])
with top_logo:
    if LOGO_PATH.exists():
        # use_container_width scales the logo to fit its column while
        # preserving aspect ratio, so it stays proportional at any
        # screen size instead of being stretched/distorted.
        st.image(str(LOGO_PATH), use_container_width=True)
    else:
        st.markdown(f"## {CFG['logo_emoji']}")
with top_l:
    st.markdown(f'<div class="app-title">{CFG["app_name"]}</div>', unsafe_allow_html=True)
    st.caption(f"Logged in as **{username}** ({role})")
    if active_source and active_source.get("name"):
        if active_source.get("kind") == "manager":
            st.markdown(f'<div class="active-source-line">📊 Currently viewing: '
                        f'<b>{active_source["name"]}</b></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="active-source-line">📊 Currently viewing: '
                        f'<b>{active_source["name"]}</b> (uploaded file)</div>', unsafe_allow_html=True)
with top_r:
    dm = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
    if dm != st.session_state.dark_mode:
        st.session_state.dark_mode = dm
        st.rerun()
    if st.button("🚪 Logout", use_container_width=True):
        auth.logout()

# ----------------------------------------------------------------------------
# LIVE SLIDESHOW TOGGLE (available to any logged-in role — it's read-only)
# ----------------------------------------------------------------------------
if st.toggle("🖥️ Live Slideshow Mode — auto-cycle every manager × all 14 tabs (15s each), full screen",
             value=False):
    st.session_state.slideshow_on = True
    st.rerun()

# ----------------------------------------------------------------------------
# ADMIN: DATA SOURCE — Upload Excel File OR Load a Manager's Google Sheet
# ----------------------------------------------------------------------------
if role == "Admin":
    with st.expander("⚙️ Admin Panel — Upload New Data File", expanded=False):
        source = st.radio(
            "Data source",
            ["📁 Upload Excel File", "🔗 Load a Manager's Google Sheet"],
            horizontal=True,
        )

        if source == "📁 Upload Excel File":
            up = st.file_uploader("Upload Excel file (.xlsx) to replace the current dataset", type=["xlsx"])
            if up is not None:
                loader.save_uploaded_file(up)
                loader.set_active_source("upload", up.name)
                st.success("✅ File uploaded, converted to JSON cache, and all dashboards refreshed!")
                st.rerun()

        else:
            managers = CFG.get("manager_reports", [])
            if not managers:
                st.info(
                    "No manager reports configured yet. Add entries under "
                    "`manager_reports` in config.json — see README.md for the format."
                )
            else:
                names = [m["name"] for m in managers]
                sel_name = st.selectbox("Select Manager", names)
                mgr = next(m for m in managers if m["name"] == sel_name)
                st.caption(f"Source: {mgr['sheet_url']}")
                if st.button(f"⬇️ Load {sel_name}'s Data Into Dashboard", use_container_width=True):
                    try:
                        raw = fetch_manager_sheet(mgr["sheet_url"])
                        loader.save_dataframe_as_source(raw)
                        loader.set_active_source("manager", sel_name)
                        st.success(f"✅ {sel_name}'s report loaded — all dashboards refreshed!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ Could not load {sel_name}'s report: {e}")

        st.markdown("---")
        st.markdown("##### 🩺 Connection Health Check")
        st.caption("Tests every manager sheet at once — useful before running the Live Slideshow, "
                   "so a permission issue on one sheet doesn't surprise you mid-cycle.")
        if st.button("🩺 Test All Manager Connections", use_container_width=True):
            managers = CFG.get("manager_reports", [])
            if not managers:
                st.info("No manager reports configured yet.")
            else:
                rows = []
                progress = st.progress(0.0)
                for i, m in enumerate(managers):
                    result = test_manager_connection(m["sheet_url"])
                    rows.append({
                        "Manager": m["name"],
                        "Status": "✅ OK" if result["ok"] else "❌ Failed",
                        "Rows": result["rows"] if result["ok"] else "—",
                        "Cols": result["cols"] if result["ok"] else "—",
                        "Details": "Fetched successfully" if result["ok"] else result["error"],
                    })
                    progress.progress((i + 1) / len(managers))
                progress.empty()
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

try:
    df = loader.load()
except Exception as e:
    st.error(f"Could not load data file: {e}")
    st.stop()

if df.empty:
    st.warning("No data available. Please upload a valid Excel file.")
    st.stop()

# ----------------------------------------------------------------------------
# SIDEBAR FILTERS (apply globally)
# ----------------------------------------------------------------------------
fdf = render_sidebar_filters(df, COLS)
if fdf.empty:
    st.warning("No records match the selected filters.")
    st.stop()

# ----------------------------------------------------------------------------
# BUILD CONTEXT + RENDER
# ----------------------------------------------------------------------------
ctx = build_context(fdf, CFG)
render_kpi_header(ctx)

tabs = st.tabs(TAB_TITLES)
for i, tab in enumerate(tabs):
    with tab:
        render_tab_content(i, ctx)

st.markdown("---")
st.caption("© Warehouse Operations Intelligence Dashboard · Built with Streamlit, Plotly & Pandas")
