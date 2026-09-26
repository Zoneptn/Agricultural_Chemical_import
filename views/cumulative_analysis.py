import streamlit as st

from common import load_master_import, load_reg_no, reload_all
from market import build_category_map, with_category
from cumulative import render_cumulative_trend, render_pareto

df_raw = load_master_import()
reg_df = load_reg_no()
df = with_category(df_raw, build_category_map(reg_df))

st.title("📈 Cumulative Analysis")
st.caption(
    "Running totals over time, and which chemicals, categories, or origin countries account "
    "for most of the import volume (a Pareto / 80-20 view)."
)

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

st.subheader("Cumulative import volume over time")
sel_names = st.multiselect(
    "Chemical(s) — leave empty for a single running total across all chemicals",
    sorted(df["common_name"].unique()),
)
render_cumulative_trend(df, sel_names)

st.divider()

st.subheader("Pareto: what drives total import volume")
dimension_label = st.radio("Break down by", ["Chemical", "Category", "Origin country"], horizontal=True)
dim_col = {"Chemical": "common_name", "Category": "category", "Origin country": "origin"}[dimension_label]
dim_plural = {"Chemical": "Chemicals", "Category": "Categories", "Origin country": "Origin countries"}[dimension_label]
top_n = st.slider("Show top N in the chart", 5, 30, 15)
render_pareto(df, dim_col, dimension_label, dim_plural, top_n)
