"""
filters.py
-----------
Builds the responsive sidebar with global filters (Date range, Month, Year,
Team Leader, Activity, Location, Category, Employee/Supervisor) and returns
the filtered DataFrame. Every page consumes the SAME filtered dataframe, so
all charts update immediately and stay in sync.
"""
import streamlit as st
import pandas as pd


def render_sidebar_filters(df: pd.DataFrame, cols: dict) -> pd.DataFrame:
    st.sidebar.markdown("## 🔍 Global Filters")

    min_d, max_d = df[cols["date"]].min().date(), df[cols["date"]].max().date()
    date_range = st.sidebar.date_input("📅 Date Range", value=(min_d, max_d),
                                        min_value=min_d, max_value=max_d)
    years = sorted(df["Year"].dropna().unique().tolist())
    sel_years = st.sidebar.multiselect("🗓️ Year", years, default=years)

    months = sorted(df["MonthName"].dropna().unique().tolist(),
                     key=lambda m: pd.to_datetime(m, format="%b %Y"))
    sel_months = st.sidebar.multiselect("📆 Month", months, default=months)

    tls = sorted(df[cols["team_leader"]].dropna().unique().tolist())
    sel_tls = st.sidebar.multiselect("👤 Team Leader", tls, default=[])

    activities = sorted(df[cols["activity"]].dropna().unique().tolist())
    sel_activities = st.sidebar.multiselect("🏷️ Activity", activities, default=[])

    locations = sorted(df[cols["location"]].dropna().unique().tolist())
    sel_locations = st.sidebar.multiselect("📍 Location", locations, default=[])

    categories = sorted(df[cols["category"]].dropna().unique().tolist())
    sel_categories = st.sidebar.multiselect("📂 Category", categories, default=[])

    employees = sorted(df[cols["supervisor"]].dropna().unique().tolist())
    sel_employees = st.sidebar.multiselect("🧑‍🔧 Employee / Supervisor", employees, default=[])

    if st.sidebar.button("♻️ Reset All Filters", use_container_width=True):
        st.rerun()

    # ---- Apply filters ----
    out = df.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        out = out[(out["DateOnly"] >= date_range[0]) & (out["DateOnly"] <= date_range[1])]
    if sel_years:
        out = out[out["Year"].isin(sel_years)]
    if sel_months:
        out = out[out["MonthName"].isin(sel_months)]
    if sel_tls:
        out = out[out[cols["team_leader"]].isin(sel_tls)]
    if sel_activities:
        out = out[out[cols["activity"]].isin(sel_activities)]
    if sel_locations:
        out = out[out[cols["location"]].isin(sel_locations)]
    if sel_categories:
        out = out[out[cols["category"]].isin(sel_categories)]
    if sel_employees:
        out = out[out[cols["supervisor"]].isin(sel_employees)]

    st.sidebar.markdown("---")
    st.sidebar.metric("Filtered Records", f"{len(out):,}", f"of {len(df):,} total")
    return out
