import streamlit as st

from common import load_reg_no, load_master_import, reload_all
from benchmark import DEFAULT_DISTRIBUTOR, distributor_options, render_benchmark

reg_df = load_reg_no()
master_df = load_master_import()

st.title("📐 SHK Benchmark")
st.caption(
    "How a distributor's registration portfolio compares to the total market — category share, "
    "who else competes in each category, and the biggest chemicals by import volume it doesn't "
    "carry. Built from reg_no's registration counts, since master_import records only a shipment's "
    "origin country and can't be tied to a specific company."
)

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

options = distributor_options(reg_df)
default_idx = options.index(DEFAULT_DISTRIBUTOR) if DEFAULT_DISTRIBUTOR in options else 0
distributor = st.selectbox("Distributor", options, index=default_idx)

if distributor != DEFAULT_DISTRIBUTOR:
    st.caption(f"Defaults to SHK ({DEFAULT_DISTRIBUTOR}) — showing \"{distributor}\" instead.")

_this_prefix = distributor.split(" ")[0]
near_dupes = [
    d for d in options
    if d != distributor and (d.split(" ")[0].startswith(_this_prefix) or _this_prefix.startswith(d.split(" ")[0]))
]
if near_dupes:
    st.caption(f"Similarly named distributor(s) also on record, kept separate here: {', '.join(near_dupes)}.")

active_only = st.checkbox("Active (non-expired) registrations only", value=True, key="bench_active_only")

st.divider()

render_benchmark(reg_df, master_df, distributor, active_only)
