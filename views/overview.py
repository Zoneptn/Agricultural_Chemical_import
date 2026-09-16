import streamlit as st

from common import load_master_import, load_reg_no, load_classifications, reload_all
from filters import render_filters, apply_filters
from charts import METRIC_LABELS, render_trend_chart, render_origin_chart, render_data_table
from registrations import render_registrations_tab
from classification import render_classification_expanders

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

year_min, year_max = int(df["year"].min()), int(df["year"].max())

row1_col1, row1_col2 = st.columns(2)
row2_col1, row2_col2 = st.columns(2)
slots = {
    "common_name": row1_col1,
    "concentration": row1_col2,
    "formulation_type": row2_col1,
    "origin": row2_col2,
}
sel = render_filters(df, slots)
sel_names = sel["common_name"]
sel_conc = sel["concentration"]
sel_form = sel["formulation_type"]

sel_years = st.slider("Year range", year_min, year_max, (year_min, year_max), key="sel_years")
filtered = apply_filters(df, sel, sel_years)

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
metric_choice = st.radio(
    "Metric", list(METRIC_LABELS.keys()), format_func=lambda k: METRIC_LABELS[k], horizontal=True
)

tab_trend, tab_origin, tab_data, tab_reg, tab_class = st.tabs(
    ["📈 Trend by year", "🌍 By origin country", "📋 Data table", "🗂️ Active registrations", "🧬 Classification"]
)

with tab_trend:
    render_trend_chart(filtered, sel_names, metric_choice)

with tab_origin:
    render_origin_chart(filtered, metric_choice)

with tab_data:
    render_data_table(filtered)

with tab_reg:
    render_registrations_tab(reg_df, sel_names, sel_conc, sel_form)

with tab_class:
    st.caption("IRAC (insecticides) / HRAC (herbicides) / FRAC (fungicides) mode-of-action lookup, matched by chemical name.")
    render_classification_expanders(sel_names, classification_tables)
