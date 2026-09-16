import pandas as pd
import plotly.express as px
import streamlit as st

from common import (
    load_master_import,
    load_reg_no,
    load_classifications,
    reload_all,
    not_expired,
    render_cross_filters,
)

st.set_page_config(page_title="Chemical Overview", layout="wide")

df = load_master_import()
reg_df = load_reg_no()
classification_tables = load_classifications()

st.title("🧪 Chemical Overview")
st.caption("Import volume by chemical, concentration, formulation, and origin country — plus active registration lookup")

# ---------------- Sidebar: reload only ----------------
st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

# ---------------- Filters (main area, fully cross-linked) ----------------
st.subheader("Filters")

FILTER_COLS = ["common_name", "concentration", "formulation_type", "origin"]
FILTER_LABELS = {
    "common_name": "Chemical (common name)",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "origin": "Origin country",
}
FILTER_KEYS = {c: f"sel_{c}" for c in FILTER_COLS}

year_min, year_max = int(df["year"].min()), int(df["year"].max())

row1_col1, row1_col2 = st.columns(2)
row2_col1, row2_col2 = st.columns(2)
slots = {
    "common_name": row1_col1,
    "concentration": row1_col2,
    "formulation_type": row2_col1,
    "origin": row2_col2,
}
sel = render_cross_filters(df, FILTER_COLS, FILTER_LABELS, FILTER_KEYS, slots)

sel_names = sel["common_name"]
sel_conc = sel["concentration"]
sel_form = sel["formulation_type"]
sel_origin = sel["origin"]

sel_years = st.slider("Year range", year_min, year_max, (year_min, year_max), key="sel_years")

filtered = df[(df["year"] >= sel_years[0]) & (df["year"] <= sel_years[1])]
if sel_names:
    filtered = filtered[filtered["common_name"].isin(sel_names)]
if sel_conc:
    filtered = filtered[filtered["concentration"].isin(sel_conc)]
if sel_form:
    filtered = filtered[filtered["formulation_type"].isin(sel_form)]
if sel_origin:
    filtered = filtered[filtered["origin"].isin(sel_origin)]

st.divider()

# ---------------- Summary metrics ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Matching rows", f"{len(filtered):,}")
c2.metric("Total quantity (kg)", f"{filtered['quantity_kg'].sum():,.0f}")
c3.metric("Total value (THB)", f"{filtered['value_bht'].sum():,.0f}")
c4.metric("Total active ingredient (kg)", f"{filtered['ai_kg'].sum():,.0f}")

st.divider()

if filtered.empty:
    st.warning("No import data matches the current filters.")
    st.stop()

# ---------------- Metric choice for chart ----------------
metric_labels = {
    "quantity_kg": "Import quantity (kg)",
    "value_bht": "Import value (THB)",
    "ai_kg": "Active ingredient (kg)",
    "price_thb": "Average price (THB/kg)",
}
metric_choice = st.radio(
    "Metric", list(metric_labels.keys()), format_func=lambda k: metric_labels[k], horizontal=True
)

tab_trend, tab_origin, tab_data, tab_reg = st.tabs(
    ["📈 Trend by year", "🌍 By origin country", "📋 Data table", "🗂️ Active registrations"]
)

# ---------------- Trend chart (line, split by chemical) ----------------
with tab_trend:
    group_cols = ["year", "common_name"] if sel_names else ["year"]

    if metric_choice == "price_thb":
        trend = filtered.groupby(group_cols, as_index=False)[["value_bht", "quantity_kg"]].sum()
        trend["price_thb"] = trend["value_bht"] / trend["quantity_kg"].replace(0, pd.NA)
        y_col = "price_thb"
    else:
        trend = filtered.groupby(group_cols, as_index=False)[metric_choice].sum()
        y_col = metric_choice

    if sel_names:
        fig = px.line(
            trend, x="year", y=y_col, color="common_name", markers=True,
            labels={"year": "Year", y_col: metric_labels[metric_choice], "common_name": "Chemical"},
        )
    else:
        fig = px.line(
            trend, x="year", y=y_col, markers=True, labels={"year": "Year", y_col: metric_labels[metric_choice]}
        )
        st.caption("Pick one or more chemicals above to split this line by chemical.")
    st.plotly_chart(fig, width='stretch')

# ---------------- Breakdown by origin ----------------
with tab_origin:
    if metric_choice == "price_thb":
        by_origin = filtered.groupby("origin", as_index=False)[["value_bht", "quantity_kg"]].sum()
        by_origin["price_thb"] = by_origin["value_bht"] / by_origin["quantity_kg"].replace(0, pd.NA)
    else:
        by_origin = filtered.groupby("origin", as_index=False)[metric_choice].sum()
    by_origin = by_origin.sort_values(metric_choice, ascending=False).head(15)

    fig2 = px.bar(
        by_origin, x=metric_choice, y="origin", orientation="h",
        labels={metric_choice: metric_labels[metric_choice], "origin": "Origin"},
    )
    fig2.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig2, width='stretch')

# ---------------- Data table ----------------
with tab_data:
    st.dataframe(filtered.sort_values("year", ascending=False), width='stretch')
    st.download_button(
        "Download filtered data as CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "filtered_chemical_import.csv",
        "text/csv",
    )

# ---------------- Active registrations (joined from reg_no) ----------------
with tab_reg:
    st.caption(
        "Matched from the reg_no sheet by chemical name (and concentration/formulation type, "
        "when selected above). Origin country isn't tracked in reg_no, so it isn't used to filter "
        "this table. Only registrations that are not expired are shown."
    )

    reg_view = not_expired(reg_df)
    if sel_names:
        reg_view = reg_view[reg_view["common_name"].str.lower().isin([n.lower() for n in sel_names])]
    if sel_conc:
        reg_view = reg_view[reg_view["concentration"].str.lower().isin([c.lower() for c in sel_conc])]
    if sel_form:
        reg_view = reg_view[reg_view["formulation_type"].str.lower().isin([f.lower() for f in sel_form])]

    if not sel_names:
        st.info("Pick a chemical above to narrow this list — showing all active registrations otherwise.")

    if reg_view.empty:
        st.warning("No active (non-expired) registrations match the current chemical/concentration/formulation filters.")
    else:
        display_cols = {
            "common_name": "Chemical",
            "concentration": "Concentration",
            "formulation_type": "Formulation type",
            "trade_name": "Trade name",
            "source": "Source",
            "register": "Register",
            "distributor": "Distributor",
            "expire": "Expires",
        }
        st.dataframe(
            reg_view[list(display_cols.keys())].rename(columns=display_cols).sort_values("Chemical"),
            width='stretch',
            hide_index=True,
        )
        st.caption(f"{len(reg_view):,} active registration(s) matched.")
        st.download_button(
            "Download active registrations as CSV",
            reg_view[list(display_cols.keys())].rename(columns=display_cols).to_csv(index=False).encode("utf-8"),
            "active_registrations.csv",
            "text/csv",
        )
