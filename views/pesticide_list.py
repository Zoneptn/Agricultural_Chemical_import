import streamlit as st

from common import load_pesticide_list, load_reg_no, load_master_import, reload_all
from pesticide_checks import render_summary, render_search, render_chemical_check, render_gaps

plist = load_pesticide_list()
reg_df = load_reg_no()
master_df = load_master_import()

st.title("📋 Pesticide List")
st.caption(
    "Check chemicals against the official pesticide list (pesticide_list sheet): which Royal Gazette "
    "announcement they come from, and how they line up with registrations and imports."
)

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

render_summary(plist)

st.divider()

tab_search, tab_check, tab_gaps = st.tabs(["Search the list", "Check a chemical", "Cross-check gaps"])
with tab_search:
    render_search(plist, reg_df, master_df)
with tab_check:
    render_chemical_check(plist, reg_df, master_df)
with tab_gaps:
    render_gaps(plist, reg_df, master_df)
