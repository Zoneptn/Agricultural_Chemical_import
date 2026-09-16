import streamlit as st

from common import load_reg_no, reload_all
from registrations import search_registrations, render_search_results

reg_df = load_reg_no()

st.title("🔎 Registration Search")
st.caption("Search Thailand agrochemical registrations by product name, registration number, chemical, category, or company.")

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

query = st.text_input(
    "Search by trade name, registration number, original name, distributor, or importer",
    placeholder="e.g. Amistar, 2554 - 19, Syngenta ...",
)

c1, c2 = st.columns(2)
with c1:
    sel_categories = st.multiselect("Category", sorted(reg_df["category"].unique()))
with c2:
    sel_names = st.multiselect("Chemical (common name)", sorted(reg_df["common_name"].unique()))

c3, c4 = st.columns(2)
with c3:
    sel_conc = st.multiselect("Concentration", sorted(reg_df["concentration"].unique()))
with c4:
    sel_form = st.multiselect("Formulation type", sorted(reg_df["formulation_type"].unique()))

active_only = st.checkbox("Show only active (non-expired) registrations", value=True)

st.divider()

results = search_registrations(reg_df, query, sel_categories, sel_names, sel_conc, sel_form, active_only)
render_search_results(results)
