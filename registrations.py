"""Active (non-expired) registration lookup, joined from reg_no by chemical name.

filter_active_registrations() computes the matching rows once; the overview
page uses that both for the always-visible summary metrics and for the
detailed table inside the "Active registrations" tab.
"""
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


def filter_active_registrations(reg_df, sel_names, sel_conc, sel_form):
    """Non-expired reg_no rows matching the current chemical/concentration/
    formulation filters. Origin country isn't tracked in reg_no, so it's not
    used here."""
    reg_view = not_expired(reg_df)
    if sel_names:
        reg_view = reg_view[reg_view["common_name"].str.lower().isin([n.lower() for n in sel_names])]
    if sel_conc:
        reg_view = reg_view[reg_view["concentration"].str.lower().isin([c.lower() for c in sel_conc])]
    if sel_form:
        reg_view = reg_view[reg_view["formulation_type"].str.lower().isin([f.lower() for f in sel_form])]
    return reg_view


SEARCH_TEXT_COLS = ["reg_no", "trade_name", "common_name", "common_name_original", "distributor", "importer"]


CHEMICAL_VARIANT_COLS = ["common_name", "concentration", "formulation_type"]
CHEMICAL_VARIANT_LABELS = {
    "common_name": "Chemical (common name)",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
}
CHEMICAL_VARIANT_KEYS = {c: f"search_{c}" for c in CHEMICAL_VARIANT_COLS}
_LAST_CHANGED_KEY = "_chem_variant_last_changed"


def _mark_changed(col):
    st.session_state[_LAST_CHANGED_KEY] = col


def _chemical_variant_options(reg_df, col, skip_narrowing=False):
    """Options for `col`, narrowed by the other two chemical-variant fields'
    current selections — unless skip_narrowing, which returns the full
    unconstrained set (used for whichever field the user just touched, so a
    stale, not-yet-reconciled other field can never make that fresh pick
    invalid or crash the widget)."""
    if skip_narrowing:
        return sorted(reg_df[col].unique())
    sub = reg_df
    for other in CHEMICAL_VARIANT_COLS:
        if other == col:
            continue
        other_sel = st.session_state.get(CHEMICAL_VARIANT_KEYS[other], [])
        if other_sel:
            sub = sub[sub[other].isin(other_sel)]
    return sorted(sub[col].unique())


def render_chemical_variant_filters(reg_df, slots):
    """Renders the chemical/concentration/formulation-type dropdowns into
    `slots` (dict col -> st column), cross-narrowed against each other.
    Whichever field the user just changed is treated as authoritative for
    this render (its own options aren't narrowed by the other two, which may
    still be stale) — the other two get narrowed and sanitized against it, so
    picking an incompatible value for a still-set field cleanly clears it
    instead of the fresh pick getting silently overridden. Returns a dict
    col -> list of selected values."""
    last_changed = st.session_state.get(_LAST_CHANGED_KEY)
    sel = {}
    for col in CHEMICAL_VARIANT_COLS:
        with slots[col]:
            opts = _chemical_variant_options(reg_df, col, skip_narrowing=(col == last_changed))
            key = CHEMICAL_VARIANT_KEYS[col]
            # drop any previously-selected values that no longer apply, so a
            # tighter set from another field never crashes the widget — but
            # never do this to the field the user just touched
            if key in st.session_state and col != last_changed:
                valid = [v for v in st.session_state[key] if v in opts]
                if valid != st.session_state[key]:
                    st.session_state[key] = valid
            sel[col] = st.multiselect(
                CHEMICAL_VARIANT_LABELS[col], opts, key=key, on_change=_mark_changed, args=(col,)
            )
    return sel


def issued_date_bounds(reg_df):
    """Min/max issued date in the data, as plain date objects for a date_input."""
    valid = reg_df["issued"].dropna()
    return valid.min().date(), valid.max().date()


def search_registrations(reg_df, query, categories, names, concs, forms, distributors, issued_from, issued_to, active_only):
    """General-purpose registration search: free-text across reg_no/trade
    name/original name/distributor/importer, plus dropdown filters for
    category, chemical, concentration, formulation type, and distributor,
    plus an issued-date range."""
    view = not_expired(reg_df) if active_only else reg_df

    if query and query.strip():
        q = query.strip().lower()
        mask = False
        for col in SEARCH_TEXT_COLS:
            mask = mask | view[col].str.lower().str.contains(q, regex=False, na=False)
        view = view[mask]

    if categories:
        view = view[view["category"].isin(categories)]
    if names:
        view = view[view["common_name"].str.lower().isin([n.lower() for n in names])]
    if concs:
        view = view[view["concentration"].str.lower().isin([c.lower() for c in concs])]
    if forms:
        view = view[view["formulation_type"].str.lower().isin([f.lower() for f in forms])]
    if distributors:
        view = view[view["distributor"].isin(distributors)]

    if issued_from and issued_to:
        issued_date = view["issued"].dt.date
        # registrations with no issued date on record are kept regardless of
        # the range — we can't disprove they belong in it
        view = view[issued_date.isna() | ((issued_date >= issued_from) & (issued_date <= issued_to))]

    return view


SEARCH_DISPLAY_COLS = {
    "reg_no": "Reg. No.",
    "category": "Category",
    "common_name": "Chemical",
    "common_name_original": "Original name",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "trade_name": "Trade name",
    "source": "Source",
    "register": "Register",
    "importer": "Importer",
    "distributor": "Distributor",
    "issued": "Issued",
    "expire": "Expires",
    "status": "Status",
}


def render_search_results(view):
    if view.empty:
        st.warning("No registrations match this search.")
        return

    display = view[list(SEARCH_DISPLAY_COLS.keys())].rename(columns=SEARCH_DISPLAY_COLS).sort_values("Chemical")
    st.caption(f"{len(view):,} registration(s) found — {view['distributor'].nunique():,} unique distributor(s).")
    st.dataframe(display, width='stretch', hide_index=True)
    st.download_button(
        "Download search results as CSV",
        display.to_csv(index=False).encode("utf-8"),
        "registration_search_results.csv",
        "text/csv",
    )


def render_registrations_tab(reg_view, sel_names):
    """Renders the detailed table for a look-up someone wants to dig into —
    the summary counts live above this tab, not repeated here."""
    st.caption(
        "Matched from the reg_no sheet by chemical name (and concentration/formulation type, "
        "when selected above). Origin country isn't tracked in reg_no, so it isn't used to filter "
        "this table. Only registrations that are not expired are shown."
    )

    if not sel_names:
        st.info("Pick a chemical above to narrow this list — showing all active registrations otherwise.")

    if reg_view.empty:
        st.warning("No active (non-expired) registrations match the current chemical/concentration/formulation filters.")
        return

    view = reg_view[list(DISPLAY_COLS.keys())].rename(columns=DISPLAY_COLS).sort_values("Chemical")
    st.dataframe(view, width='stretch', hide_index=True)
    st.download_button(
        "Download active registrations as CSV",
        view.to_csv(index=False).encode("utf-8"),
        "active_registrations.csv",
        "text/csv",
    )
