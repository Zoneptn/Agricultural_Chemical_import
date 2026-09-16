"""Cross-linked filter widgets for the Chemical Overview page."""
import streamlit as st

FILTER_COLS = ["common_name", "concentration", "formulation_type", "origin"]
FILTER_LABELS = {
    "common_name": "Chemical (common name)",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "origin": "Origin country",
}
FILTER_KEYS = {c: f"sel_{c}" for c in FILTER_COLS}


def cross_filter_options(df, col):
    """Options for `col`, narrowed by every OTHER filter's current session_state
    selection, so any filter can narrow any other regardless of pick order."""
    sub = df
    for other in FILTER_COLS:
        if other == col:
            continue
        other_sel = st.session_state.get(FILTER_KEYS[other], [])
        if other_sel:
            sub = sub[sub[other].isin(other_sel)]
    return sorted(sub[col].unique())


def render_filters(df, slots):
    """Renders one multiselect per FILTER_COLS entry into `slots` (dict col ->
    st column), cross-narrowing options against every other filter's current
    selection. Returns a dict col -> list of selected values."""
    sel = {}
    for col in FILTER_COLS:
        with slots[col]:
            opts = cross_filter_options(df, col)
            key = FILTER_KEYS[col]
            # drop any previously-selected values that no longer apply, so a
            # tighter set from another filter never crashes the widget
            if key in st.session_state:
                valid = [v for v in st.session_state[key] if v in opts]
                if valid != st.session_state[key]:
                    st.session_state[key] = valid
            sel[col] = st.multiselect(FILTER_LABELS[col], opts, key=key)
            if len(opts) == 1:
                st.caption(f"Only one {FILTER_LABELS[col].lower()} matches the other filters.")
    return sel


def apply_filters(df, sel, sel_years):
    """Applies the year range plus every non-empty filter selection to df."""
    filtered = df[(df["year"] >= sel_years[0]) & (df["year"] <= sel_years[1])]
    for col in FILTER_COLS:
        if sel.get(col):
            filtered = filtered[filtered[col].isin(sel[col])]
    return filtered
