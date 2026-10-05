import streamlit as st

from common import load_pesticide_list, load_reg_no, load_master_import, reload_all
from pesticide_checks import render_summary, render_chemical_check, render_gaps

plist = load_pesticide_list()
reg_df = load_reg_no()
master_df = load_master_import()

st.title("📋 Pesticide List")
st.caption(
    "Check a chemical or a combination (A+B, A+B+C) against the official pesticide list (pesticide_list sheet), "
    "and see how it compares with each ingredient on its own, with registrations, and with imports."
)

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

render_summary(plist)

st.divider()

render_chemical_check(plist, reg_df, master_df)

st.divider()

with st.expander("Cross-check gaps between the list, registrations and imports"):
    render_gaps(plist, reg_df, master_df)
