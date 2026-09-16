import streamlit as st

from common import load_master_import, load_classifications, reload_all
from charts import METRIC_LABELS
from comparison import (
    render_slot_pickers,
    build_combined_frame,
    render_comparison_trend,
    render_comparison_summary,
    render_comparison_classification,
)

st.set_page_config(page_title="Chemical Comparison", layout="wide")

df = load_master_import()
classification_tables = load_classifications()

st.title("🔬 Chemical Comparison")
st.caption(
    "Compare chemicals side by side over the full year range — including the same "
    "chemical from different origin countries."
)

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

metric_choice = st.radio(
    "Metric", list(METRIC_LABELS.keys()), format_func=lambda k: METRIC_LABELS[k], horizontal=True
)

num_chem = st.slider("Number of chemicals to compare", min_value=2, max_value=10, value=3, key="cmp_num")

specs = render_slot_pickers(df, num_chem)

st.divider()

if not specs:
    st.info("Pick at least one chemical above (in any slot) to see the comparison.")
    st.stop()

combined = build_combined_frame(df, specs)

if combined.empty:
    st.warning("None of the selected chemical/country combinations have any import data.")
    st.stop()

st.subheader(f"{METRIC_LABELS[metric_choice]} by year")
render_comparison_trend(combined, metric_choice, METRIC_LABELS)

st.markdown("**Summary totals**")
render_comparison_summary(combined)

st.markdown("**Classification detail (IRAC / HRAC / FRAC)**")
render_comparison_classification(specs, classification_tables)
