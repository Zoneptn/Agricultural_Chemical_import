import streamlit as st

from common import load_master_import, load_reg_no, load_classifications, reload_all
from market import (
    render_keyword_aggregation,
    render_category_trend,
    render_origin_market_share,
    render_concentration_index,
    render_movers_table,
)
from aggregate import render_product_aggregation, render_group_aggregation

df = load_master_import()
reg_df = load_reg_no()

st.title("📊 Market Summary")
st.caption("Keyword rollups, category trends, origin-country market share, and year-over-year movers across all chemical imports.")

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

st.subheader("Aggregate imports")
tab_kw, tab_prod, tab_group = st.tabs(["By keyword", "By specific products", "By IRAC / HRAC / FRAC group"])
with tab_kw:
    render_keyword_aggregation(df, reg_df)
with tab_prod:
    render_product_aggregation(df)
with tab_group:
    render_group_aggregation(df, load_classifications())

st.divider()

st.subheader("Total import volume by category")
sel_categories = st.multiselect(
    "Category (leave empty to show all)", sorted(df["category"].unique())
)
render_category_trend(df, sel_categories)

st.divider()

st.subheader("Top export countries to Thailand")
render_origin_market_share(df)

st.divider()

st.subheader("Market concentration by category")
render_concentration_index(df)

st.divider()

st.subheader("Movers: biggest year-over-year change in import quantity")
years = sorted(df["year"].unique())
eligible_years = years[1:]  # need a prior year to compare against
current_year = st.selectbox("Compare year", eligible_years, index=len(eligible_years) - 1)
prior_year = years[years.index(current_year) - 1]
st.caption(f"Comparing {current_year} against {prior_year}.")
render_movers_table(df, current_year, prior_year)
