"""Active (non-expired) registration lookup, joined from reg_no by chemical name."""
import streamlit as st

from common import not_expired

DISPLAY_COLS = {
    "common_name": "Chemical",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "trade_name": "Trade name",
    "source": "Source",
    "register": "Register",
    "distributor": "Distributor",
    "expire": "Expires",
}


def render_registrations_tab(reg_df, sel_names, sel_conc, sel_form):
    st.caption(
        "Matched from the reg_no sheet by chemical name (and concentration/formulation type, "
        "when selected above). Origin country isn't tracked in reg_no, so it isn't used to filter "
        "this table. Only registrations that are not expired are shown."
    )

    reg_view = not_expired(reg_df)
    if sel_names:
        reg_view = reg_view[reg_view["common_name"].str.lower().isin([n.lower() for n in sel_names])]
    if sel_conc:
        reg_view = reg_view[reg_view["concentration"].str.lower().isin([c.lower() for c in sel_conc])]
    if sel_form:
        reg_view = reg_view[reg_view["formulation_type"].str.lower().isin([f.lower() for f in sel_form])]

    if not sel_names:
        st.info("Pick a chemical above to narrow this list — showing all active registrations otherwise.")

    if reg_view.empty:
        st.warning("No active (non-expired) registrations match the current chemical/concentration/formulation filters.")
        return

    view = reg_view[list(DISPLAY_COLS.keys())].rename(columns=DISPLAY_COLS).sort_values("Chemical")

    c1, c2 = st.columns(2)
    c1.metric("Active registrations matched", f"{len(reg_view):,}")
    c2.metric("Unique distributors", f"{reg_view['distributor'].nunique():,}")

    st.dataframe(view, width='stretch', hide_index=True)
    st.download_button(
        "Download active registrations as CSV",
        view.to_csv(index=False).encode("utf-8"),
        "active_registrations.csv",
        "text/csv",
    )
