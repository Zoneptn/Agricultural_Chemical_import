"""Cross-linked filter widgets for the Chemical Overview page.

The chemical picker is single-select here on purpose — comparing several
chemicals side by side lives on the separate Chemical Comparison page.
Concentration, formulation type, and origin stay multi-select since it's
normal to want several of those at once for one chemical.
"""
import streamlit as st

FILTER_COLS = ["common_name", "concentration", "formulation_type", "origin"]
FILTER_LABELS = {
    "common_name": "Chemical (common name)",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "origin": "Origin country",
}
FILTER_KEYS = {c: f"sel_{c}" for c in FILTER_COLS}

ALL_CHEMICALS = "All chemicals"


def _current_selection(col):
    """Current selection for `col` as a list, regardless of whether the widget
    behind it is the single-select chemical dropdown or a multiselect."""
    key = FILTER_KEYS[col]
    if col == "common_name":
        val = st.session_state.get(key, ALL_CHEMICALS)
        return [] if val == ALL_CHEMICALS else [val]
    return st.session_state.get(key, [])


def cross_filter_options(df, col):
    """Options for `col`, narrowed by every OTHER filter's current selection,
    so any filter can narrow any other regardless of pick order."""
    sub = df
    for other in FILTER_COLS:
        if other == col:
            continue
        other_sel = _current_selection(other)
        if other_sel:
            sub = sub[sub[other].isin(other_sel)]
    return sorted(sub[col].unique())


def render_filters(df, slots):
    """Renders the chemical dropdown (single-select) and the other three
    filters (multiselect) into `slots` (dict col -> st column), cross-narrowing
    options against every other filter's current selection. Returns a dict
    col -> list of selected values (0 or 1 items for common_name)."""
    sel = {}
    for col in FILTER_COLS:
        with slots[col]:
            opts = cross_filter_options(df, col)
            key = FILTER_KEYS[col]

            if col == "common_name":
                choices = [ALL_CHEMICALS] + opts
                if st.session_state.get(key, ALL_CHEMICALS) not in choices:
                    st.session_state[key] = ALL_CHEMICALS
                picked = st.selectbox(FILTER_LABELS[col], choices, key=key)
                sel[col] = [] if picked == ALL_CHEMICALS else [picked]
            else:
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


def clear_filters(year_min, year_max):
    """Resets every filter widget back to its default: "All chemicals",
    empty for the other multiselects, and the full year range."""
    for col in FILTER_COLS:
        key = FILTER_KEYS[col]
        st.session_state[key] = ALL_CHEMICALS if col == "common_name" else []
    st.session_state["sel_years"] = (year_min, year_max)
