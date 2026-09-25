import streamlit as st

from common import load_reg_no, reload_all
from registrations import search_registrations, render_search_results, issued_date_bounds, render_chemical_variant_filters

reg_df = load_reg_no()
issued_min, issued_max = issued_date_bounds(reg_df)

st.title("🔎 Registration Search")
st.caption("Search Thailand agrochemical registrations by product name, registration number, chemical, category, company, or issue date.")

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

query = st.text_input(
    "Search by chemical name, trade name, registration number, original name, distributor, or importer",
    placeholder="e.g. glyphosate, Amistar, 2554 - 19, Syngenta ...",
)

c1, c2 = st.columns(2)
with c1:
    sel_categories = st.multiselect("Category", sorted(reg_df["category"].unique()))

row1_c2 = c2
row2_c1, row2_c2 = st.columns(2)
slots = {"common_name": row1_c2, "concentration": row2_c1, "formulation_type": row2_c2}
sel = render_chemical_variant_filters(reg_df, slots)
sel_names = sel["common_name"]
sel_conc = sel["concentration"]
sel_form = sel["formulation_type"]

sel_distributors = st.multiselect("Distributor", sorted(reg_df["distributor"].unique()))

if "search_issued_range" not in st.session_state:
    st.session_state["search_issued_range"] = (issued_min, issued_max)
date_range = st.date_input(
    "Issued date range", min_value=issued_min, max_value=issued_max, key="search_issued_range"
)
# date_input can briefly return a single date mid-click, before the user has
# picked the second end of the range — fall back to the full range then
if isinstance(date_range, tuple) and len(date_range) == 2:
    issued_from, issued_to = date_range
else:
    issued_from, issued_to = issued_min, issued_max
st.caption("Registrations with no issued date on record are always included, regardless of this range.")

active_only = st.checkbox("Show only active (non-expired) registrations", value=True)

st.divider()

results = search_registrations(
    reg_df, query, sel_categories, sel_names, sel_conc, sel_form, sel_distributors, issued_from, issued_to, active_only
)
render_search_results(results)
