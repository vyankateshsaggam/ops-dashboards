"""
charts.py — all overlap, legend, gauge-undefined, and cut-off issues fixed.
"""
import math
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

PALETTE = ["#7C3AED", "#06B6D4", "#F59E0B", "#10B981", "#EF4444",
           "#3B82F6", "#EC4899", "#84CC16", "#F97316", "#14B8A6"]

DARK = lambda: st.session_state.get("dark_mode", True)
TPL  = lambda: "plotly_dark" if DARK() else "plotly_white"


def _truncate(label, maxlen=30):
    """Shorten very long category names (e.g. some Activity names run
    35-40+ characters) so a single legend entry can't blow out the
    reserved legend width on its own."""
    s = str(label)
    return s if len(s) <= maxlen else s[: maxlen - 1] + "…"


def _limit_slices(df, names_col, values_col, max_slices=10):
    """For pie/donut charts: cap the number of legend entries by keeping
    the top N slices (by value) and folding the rest into a single
    'Other' slice. Without this, files with many distinct categories
    (e.g. 30-40 Activities) produce legends that overflow their space and
    visually collide with the chart itself."""
    if names_col not in df.columns or values_col not in df.columns:
        return df
    d = df[[names_col, values_col]].copy()
    d[values_col] = pd.to_numeric(d[values_col], errors="coerce").fillna(0)
    d = d.groupby(names_col, as_index=False)[values_col].sum()
    d = d.sort_values(values_col, ascending=False)
    if len(d) <= max_slices:
        d[names_col] = d[names_col].map(_truncate)
        return d
    top = d.iloc[:max_slices].copy()
    other_sum = d.iloc[max_slices:][values_col].sum()
    top[names_col] = top[names_col].map(_truncate)
    if other_sum > 0:
        other_row = pd.DataFrame({names_col: [f"Other ({len(d) - max_slices})"], values_col: [other_sum]})
        top = pd.concat([top, other_row], ignore_index=True)
    return top


def _cap_color_categories(df, color_col, max_categories=10):
    """For scatter/bubble charts: if the color column has more distinct
    values than fit comfortably in a legend, keep the most frequent N and
    relabel the rest 'Other' so the legend stays a fixed, readable size no
    matter how many categories the underlying data has."""
    if not color_col or color_col not in df.columns:
        return df
    df = df.copy()
    if df[color_col].nunique() <= max_categories:
        df[color_col] = df[color_col].map(_truncate)
        return df
    top_vals = df[color_col].value_counts().head(max_categories).index
    df[color_col] = df[color_col].where(df[color_col].isin(top_vals), "Other").map(_truncate)
    return df


def base_layout(fig, height=400, title=None, margin=None, legend_override=None):
    """Base layout — does NOT touch gauge titles (they set their own).

    FIX 1: the legend used to sit at a fixed position below the plot
    (y=-0.38). With many/long x-axis category labels, Plotly's automargin
    grows the bottom tick-label area, but that fixed legend position does
    NOT move with it — so the legend ends up floating on top of the tick
    labels once there are enough categories. Moving the legend above the
    plot (stacked under the title, both within the top margin) means
    neither ever depends on how tall the x-axis label area gets, no
    matter how many categories the data has.

    FIX 2: margins/fonts used to be FIXED pixel values regardless of the
    chart's requested `height`. That's fine at the normal ~420px height,
    but at the slideshow's much shorter heights (~200px) those same fixed
    margins (t=78, b=110 = 188px) ate almost the ENTIRE canvas, leaving
    the actual plot area only a few pixels tall — which is exactly what
    made short charts unreadable/overlapping. Margins and font sizes now
    scale down proportionally with height (never below a legible floor),
    so a short chart gets a proportionally short margin, not the same
    fixed one a tall chart uses.
    """
    scale = max(0.55, min(1.0, height / 420.0))
    title_font  = max(11, round(15 * scale))
    legend_font = max(8,  round(11 * scale))
    body_font   = max(9,  round(12 * scale))

    m = margin or dict(
        l=round(30 * scale), r=round(30 * scale),
        t=round((34 if title else 10) + 28 * scale),
        b=round(110 * scale),
    )
    leg = legend_override or dict(
        orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5,
        font=dict(size=legend_font), bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        template=TPL(),
        height=height,
        title=dict(text=title, font=dict(size=title_font, family="Inter,sans-serif"),
                   x=0.01, xanchor="left", y=0.98, yanchor="top") if title else None,
        margin=m,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=leg,
        font=dict(family="Inter,sans-serif", size=body_font),
        colorway=PALETTE,
    )
    return fig


# ── KPI CARD ──────────────────────────────────────────────────────────────────
def kpi_card(label, value, sub="", icon="📊", gradient=("#7C3AED", "#06B6D4")):
    st.markdown(
        f"""<div class="kpi-card" style="background:linear-gradient(135deg,{gradient[0]},{gradient[1]});">
            <div class="kpi-icon">{icon}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""",
        unsafe_allow_html=True,
    )


# ── LINE CHART ─────────────────────────────────────────────────────────────────
def line_chart(df, x, y, color=None, title=None, height=420):
    fig = px.line(df, x=x, y=y, color=color, markers=True)
    fig.update_traces(line=dict(width=2.5))
    fig.update_layout(xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=11)))
    return base_layout(fig, height, title)


# ── AREA CHART ─────────────────────────────────────────────────────────────────
def area_chart(df, x, y, color=None, title=None, height=420):
    fig = px.area(df, x=x, y=y, color=color)
    fig.update_layout(xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=11)))
    return base_layout(fig, height, title)


# ── BAR CHART ──────────────────────────────────────────────────────────────────
def bar_chart(df, x, y, color=None, title=None, height=440,
              orientation="v", text_auto=True):
    fig = px.bar(df, x=x, y=y, color=color,
                 orientation=orientation, text_auto=text_auto)
    fig.update_traces(marker_line_width=0, textfont_size=9)
    fig.update_layout(
        xaxis=dict(tickangle=-45, automargin=True, tickfont=dict(size=10)),
        uniformtext_minsize=7,
        uniformtext_mode="hide",
    )
    return base_layout(fig, height, title)


# ── DONUT CHART ────────────────────────────────────────────────────────────────
def donut_chart(df, names, values, title=None, height=440, max_slices=10):
    # At short (slideshow) heights, a 10-row legend needs more vertical
    # room than the chart has — cap fewer slices and shrink legend text
    # proportionally so the whole legend fits instead of being clipped.
    scale = max(0.55, min(1.0, height / 440.0))
    slices = max_slices if height >= 380 else max(4, round(max_slices * scale))
    df = _limit_slices(df, names, values, max_slices=slices)
    fig = px.pie(df, names=names, values=values, hole=0.50)
    fig.update_traces(
        textposition="inside",
        textinfo="percent",
        insidetextorientation="radial",
        textfont_size=max(7, round(10 * scale)),
    )
    return base_layout(
        fig, height, title,
        margin=dict(l=10, r=180, t=round(55 * scale) + 10, b=round(20 * scale)),
        legend_override=dict(
            orientation="v", x=1.02, y=0.5,
            font=dict(size=max(7, round(10 * scale))), bgcolor="rgba(0,0,0,0)",
        ),
    )


# ── PIE CHART ──────────────────────────────────────────────────────────────────
def pie_chart(df, names, values, title=None, height=420, max_slices=10):
    scale = max(0.55, min(1.0, height / 420.0))
    slices = max_slices if height >= 380 else max(4, round(max_slices * scale))
    df = _limit_slices(df, names, values, max_slices=slices)
    fig = px.pie(df, names=names, values=values)
    fig.update_traces(
        textposition="inside",
        textinfo="percent",
        insidetextorientation="radial",
        textfont_size=max(7, round(10 * scale)),
    )
    return base_layout(
        fig, height, title,
        margin=dict(l=10, r=180, t=round(55 * scale) + 10, b=round(20 * scale)),
        legend_override=dict(
            orientation="v", x=1.02, y=0.5,
            font=dict(size=max(7, round(10 * scale))), bgcolor="rgba(0,0,0,0)",
        ),
    )


# ── SCATTER CHART ──────────────────────────────────────────────────────────────
def scatter_chart(df, x, y, color=None, size=None, title=None, height=440, max_color_categories=10):
    df = df.copy()
    # FIX: clean x and y columns
    if x in df.columns:
        df[x] = pd.to_numeric(df[x], errors="coerce").fillna(0).clip(lower=0)
    if y in df.columns:
        df[y] = pd.to_numeric(df[y], errors="coerce").fillna(0).clip(lower=0)
    # FIX: size column cannot have NaN — Plotly rejects it
    if size and size in df.columns:
        df[size] = pd.to_numeric(df[size], errors="coerce").fillna(0).clip(lower=0)
    scale = max(0.55, min(1.0, height / 440.0))
    max_cats = max_color_categories if height >= 380 else max(4, round(max_color_categories * scale))
    # FIX: cap categorical color legend so it can't overflow onto the plot
    if color:
        df = _cap_color_categories(df, color, max_categories=max_cats)
    fig = px.scatter(df, x=x, y=y, color=color, size=size, opacity=0.75)
    return base_layout(
        fig, height, title,
        margin=dict(l=round(30 * scale), r=round(30 * scale), t=round(55 * scale) + 5, b=round(60 * scale)),
        legend_override=dict(
            orientation="v", x=1.01, y=1,
            font=dict(size=max(7, round(10 * scale))), bgcolor="rgba(0,0,0,0.35)",
            borderwidth=0,
        ),
    )


# ── BUBBLE CHART ───────────────────────────────────────────────────────────────
def bubble_chart(df, x, y, size, color=None, title=None, height=500, max_color_categories=10):
    df = df.copy()
    # FIX: clean all numeric columns — NaN in size crashes Plotly
    for col in [x, y, size]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)
    scale = max(0.55, min(1.0, height / 500.0))
    max_cats = max_color_categories if height >= 420 else max(4, round(max_color_categories * scale))
    # FIX: cap categorical color legend so it can't overflow onto the plot
    if color:
        df = _cap_color_categories(df, color, max_categories=max_cats)
    fig = px.scatter(df, x=x, y=y, size=size, color=color,
                     size_max=55, opacity=0.7)
    fig.update_layout(xaxis=dict(tickangle=-30, automargin=True))
    return base_layout(
        fig, height, title,
        margin=dict(l=round(30 * scale), r=round(30 * scale), t=round(55 * scale) + 5, b=round(60 * scale)),
        legend_override=dict(
            orientation="v", x=1.01, y=1,
            font=dict(size=max(7, round(9 * scale))), bgcolor="rgba(0,0,0,0.35)",
            borderwidth=0, tracegroupgap=2,
        ),
    )


# ── HEATMAP ────────────────────────────────────────────────────────────────────
def heatmap_chart(df, x, y, z, title=None, height=460):
    pivot = df.pivot_table(index=y, columns=x, values=z, aggfunc="mean").fillna(0)
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index,
        colorscale="Viridis", colorbar=dict(title=z),
    ))
    fig.update_layout(
        xaxis=dict(tickangle=-45, automargin=True, tickfont=dict(size=10)),
        yaxis=dict(automargin=True, tickfont=dict(size=10)),
    )
    return base_layout(fig, height, title)


# ── TREEMAP ────────────────────────────────────────────────────────────────────
def treemap_chart(df, path, values, title=None, height=460,
                  color=None, color_continuous_scale="Tealgrn"):
    df = df.copy()
    for col in path:
        df = df[df[col].notna() & (df[col].astype(str).str.strip() != "")]
    agg = {values: "sum"}
    if color and color != values:
        agg[color] = "sum"
    df = df.groupby(path, as_index=False).agg(agg)
    if df.empty or df[values].sum() == 0:
        return base_layout(go.Figure(), height, title)
    fig = px.treemap(df, path=path, values=values,
                     color=color, color_continuous_scale=color_continuous_scale)
    fig.update_traces(textfont_size=13)
    return base_layout(fig, height, title)


# ── SUNBURST ───────────────────────────────────────────────────────────────────
def sunburst_chart(df, path, values, title=None, height=500):
    df = df.copy()
    for col in path:
        df = df[df[col].notna() & (df[col].astype(str).str.strip() != "")]
    df = df.groupby(path, as_index=False).agg({values: "sum"})
    if df.empty or df[values].sum() == 0:
        return base_layout(go.Figure(), height, title)
    fig = px.sunburst(df, path=path, values=values)
    fig.update_traces(textfont_size=11, insidetextorientation="radial")
    return base_layout(fig, height, title)


# ── SANKEY ─────────────────────────────────────────────────────────────────────
def sankey_chart(labels, source, target, value, title=None, height=520):
    fig = go.Figure(data=[go.Sankey(
        node=dict(pad=20, thickness=18,
                  line=dict(color="black", width=0.3),
                  label=labels, color=PALETTE * 10),
        link=dict(source=source, target=target, value=value),
        textfont=dict(size=11),
    )])
    return base_layout(fig, height, title)


# ── WATERFALL ──────────────────────────────────────────────────────────────────
def waterfall_chart(x, y, title=None, height=420, measure=None):
    fig = go.Figure(go.Waterfall(
        x=x, y=y,
        measure=measure or ["relative"] * len(x),
        connector=dict(line=dict(color="rgba(150,150,150,0.4)")),
        increasing=dict(marker=dict(color="#10B981")),
        decreasing=dict(marker=dict(color="#EF4444")),
        totals=dict(marker=dict(color="#7C3AED")),
        textfont=dict(size=11),
    ))
    return base_layout(fig, height, title)


# ── GAUGE CHART ────────────────────────────────────────────────────────────────
# FIX: gauge does NOT use base_layout (which wipes the title).
# It sets its own complete layout so "undefined" never appears.
def gauge_chart(value, title="", max_value=100, height=320, suffix="%"):
    # Sanitise value — NaN/None → 0
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            v = 0.0
    except (TypeError, ValueError):
        v = 0.0

    # Auto-extend max_value so the needle is never clipped
    effective_max = max(max_value, math.ceil(v / 10) * 10 + 10) if v > max_value else max_value

    scale = max(0.55, min(1.0, height / 320.0))
    color = "#10B981" if v >= 90 else ("#F59E0B" if v >= 70 else "#EF4444")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=v,
        number={"suffix": suffix, "font": {"size": max(16, round(30 * scale)), "color": "#F9FAFB"}},
        title={"text": title, "font": {"size": max(10, round(14 * scale)), "color": "#F9FAFB"}},
        gauge={
            "axis": {"range": [0, effective_max],
                     "tickfont": {"size": max(7, round(10 * scale))}},
            "bar": {"color": color},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0,                       effective_max * 0.70], "color": "rgba(239,68,68,0.15)"},
                {"range": [effective_max * 0.70,    effective_max * 0.90], "color": "rgba(245,158,11,0.15)"},
                {"range": [effective_max * 0.90,    effective_max],        "color": "rgba(16,185,129,0.15)"},
            ],
        },
    ))
    fig.update_layout(
        template=TPL(),
        height=height,
        margin=dict(l=round(30 * scale), r=round(30 * scale), t=round(40 * scale), b=round(20 * scale)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter,sans-serif"),
    )
    return fig


# ── RADAR CHART ────────────────────────────────────────────────────────────────
def radar_chart(categories, values_dict, title=None, height=420):
    fig = go.Figure()
    for name, vals in values_dict.items():
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=categories + [categories[0]],
            fill="toself", name=name,
        ))
    fig.update_layout(polar=dict(radialaxis=dict(
        visible=True, tickfont=dict(size=10),
    )))
    return base_layout(fig, height, title)
