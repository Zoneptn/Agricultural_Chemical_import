import streamlit as st

from common import load_master_import, load_reg_no, reload_all
from market import (
    build_category_map,
    with_category,
    render_keyword_aggregation,
    render_category_trend,
    render_origin_market_share,
    render_movers_table,
)

df_raw = load_master_import()
reg_df = load_reg_no()
category_map = build_category_map(reg_df)
df = with_category(df_raw, category_map)

st.title("📊 Market Summary")
st.caption("Keyword rollups, category trends, origin-country market share, and year-over-year movers across all chemical imports.")

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

st.subheader("Aggregate by keyword")
render_keyword_aggregation(df)

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

st.subheader("Movers: biggest year-over-year change in import quantity")
years = sorted(df["year"].unique())
eligible_years = years[1:]  # need a prior year to compare against
current_year = st.selectbox("Compare year", eligible_years, index=len(eligible_years) - 1)
prior_year = years[years.index(current_year) - 1]
st.caption(f"Comparing {current_year} against {prior_year}.")
render_movers_table(df, current_year, prior_year)
