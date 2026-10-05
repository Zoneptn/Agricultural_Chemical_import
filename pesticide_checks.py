"""Pesticide list checks: look up chemicals on the official pesticide list
(pesticide_list sheet) and compare them with reg_no and master_import.

Matching is on a normalized key (lower-case, all whitespace removed), so
"1-naphthylacetic acid" and "1-naphthylaceticacid" count as the same
chemical. Two match levels are used throughout:
  - exact product: same chemical + concentration + formulation type
  - chemical: same chemical name, any strength or formulation
"""
import re

import pandas as pd
import streamlit as st

from common import not_expired

AWAITING = "Awaiting announcement"


def _key(series):
    return series.fillna("").astype(str).str.lower().str.replace(r"\s+", "", regex=True)


def add_keys(df):
    out = df.copy()
    out["_name"] = _key(out["common_name"])
    out["_prod"] = out["_name"] + "|" + _key(out["concentration"]) + "|" + _key(out["formulation_type"])
    return out


def gazette_order(volumes):
    """Announcement No. 1, 2, ... in numeric order, 'Awaiting announcement'
    and anything else after."""
    def sort_key(v):
        m = re.search(r"No\.\s*(\d+)", v)
        return (0, int(m.group(1))) if m else (1, 0)
    return sorted(set(volumes), key=sort_key)


def list_with_matches(plist, reg_df, master_df, active_only):
    """Each list entry with: active registrations for the exact product,
    registrations for the same chemical (any strength), and total import kg
    for the same chemical."""
    pl = add_keys(plist)
    regs = add_keys(not_expired(reg_df) if active_only else reg_df)
    exact = regs.groupby("_prod")["reg_no"].nunique().rename("Registrations (exact product)")
    by_name = regs.groupby("_name")["reg_no"].nunique().rename("Registrations (same chemical)")
    imp = add_keys(master_df).groupby("_name")["quantity_kg"].sum().rename("Imported kg (same chemical)")
    pl = pl.join(exact, on="_prod").join(by_name, on="_name").join(imp, on="_name")
    for c in ["Registrations (exact product)", "Registrations (same chemical)"]:
        pl[c] = pl[c].fillna(0).astype(int)
    pl["Imported kg (same chemical)"] = pl["Imported kg (same chemical)"].fillna(0)
    return pl


SHOW_COLS = {
    "common_name": "Chemical", "concentration": "Concentration", "formulation_type": "Formulation type",
    "royal_gazette_volume": "Gazette volume",
}
MATCH_COLS = ["Registrations (exact product)", "Registrations (same chemical)", "Imported kg (same chemical)"]
COLUMN_CONFIG = {"Imported kg (same chemical)": st.column_config.NumberColumn(format="%,.0f")}


def _search(pl, query, volumes, forms):
    out = pl
    if query.strip():
        q = re.sub(r"\s+", "", query.strip().lower())
        out = out[out["_name"].str.contains(q, regex=False)]
    if volumes:
        out = out[out["royal_gazette_volume"].isin(volumes)]
    if forms:
        out = out[out["formulation_type"].isin(forms)]
    return out


def render_summary(plist):
    c1, c2, c3 = st.columns(3)
    c1.metric("Entries on the list", f"{len(plist):,}")
    c2.metric("Distinct chemicals", f"{plist['common_name'].nunique():,}")
    c3.metric("Awaiting announcement", f"{(plist['royal_gazette_volume'] == AWAITING).sum():,}")
    counts = plist["royal_gazette_volume"].value_counts()
    counts = counts.reindex(gazette_order(counts.index))
    st.caption("Entries per Royal Gazette announcement")
    st.bar_chart(counts)


def render_search(plist, reg_df, master_df):
    active_only = st.checkbox(
        "Count only active (non-expired) registrations", value=True, key="plist_active_only"
    )
    pl = list_with_matches(plist, reg_df, master_df, active_only)

    query = st.text_input(
        "Search by chemical name", placeholder="e.g. glyphosate, abamectin, 2,4-d ...", key="plist_query"
    )
    c1, c2 = st.columns(2)
    with c1:
        volumes = st.multiselect("Gazette volume", gazette_order(plist["royal_gazette_volume"]), key="plist_volumes")
    with c2:
        forms = st.multiselect("Formulation type", sorted(plist["formulation_type"].unique()), key="plist_forms")
    only_unregistered = st.checkbox(
        "Only entries with no registration for the exact product", value=False, key="plist_unreg"
    )

    res = _search(pl, query, volumes, forms)
    if only_unregistered:
        res = res[res["Registrations (exact product)"] == 0]

    st.caption(f"{len(res):,} of {len(pl):,} list entries")
    if res.empty:
        st.info("No list entries match these filters.")
        return
    table = res.rename(columns=SHOW_COLS)[list(SHOW_COLS.values()) + MATCH_COLS]
    st.dataframe(table, hide_index=True, column_config=COLUMN_CONFIG)
    st.download_button(
        "⬇️ Download as CSV", table.to_csv(index=False).encode("utf-8-sig"),
        file_name="pesticide_list_check.csv", mime="text/csv", key="plist_dl",
    )
    st.caption(
        "“Exact product” = same chemical, concentration and formulation type as the list entry. "
        "“Same chemical” = same chemical name with any strength or formulation. "
        "Imported kg is the all-years total for the chemical name in master_import."
    )


def render_chemical_check(plist, reg_df, master_df):
    placeholder = "— Select —"
    choices = [placeholder] + sorted(plist["common_name"].unique())
    if st.session_state.get("plist_chem") not in choices:
        st.session_state["plist_chem"] = placeholder
    chem = st.selectbox("Chemical on the pesticide list", choices, key="plist_chem")
    if chem == placeholder:
        st.info("Pick a chemical to see its list entries, registered products and imports.")
        return

    name_key = re.sub(r"\s+", "", chem.lower())
    pl = add_keys(plist)
    entries = pl[pl["_name"] == name_key]
    st.markdown("**On the pesticide list**")
    st.dataframe(
        entries.rename(columns=SHOW_COLS)[list(SHOW_COLS.values())], hide_index=True
    )

    regs = add_keys(reg_df)
    regs = regs[regs["_name"] == name_key].copy()
    st.markdown("**Registered products for this chemical**")
    if regs.empty:
        st.warning("No registrations found for this chemical in reg_no.")
    else:
        listed = set(entries["_prod"])
        regs["On list?"] = regs["_prod"].map(lambda p: "Yes" if p in listed else "Strength/formulation not listed")
        expired = regs["expire"].notna() & (regs["expire"] < pd.Timestamp.today().normalize())
        regs["Active"] = (~expired).map({True: "Yes", False: "Expired"})
        cols = {
            "reg_no": "Reg. No.", "trade_name": "Trade name", "concentration": "Concentration",
            "formulation_type": "Formulation type", "distributor": "Distributor", "source": "Source",
            "issued": "Issued", "expire": "Expires", "Active": "Active", "On list?": "On list?",
        }
        view = regs.rename(columns=cols)[list(cols.values())].sort_values(["On list?", "Concentration"])
        n_off = (regs["On list?"] != "Yes").sum()
        st.caption(f"{len(regs):,} registration rows; {n_off:,} not matching a list entry on strength/formulation.")
        st.dataframe(view, hide_index=True)

    imp = add_keys(master_df)
    imp = imp[imp["_name"] == name_key]
    st.markdown("**Imports of this chemical**")
    if imp.empty:
        st.info("No imports recorded for this chemical in master_import.")
    else:
        by_year = imp.groupby("year", as_index=False)["quantity_kg"].sum().rename(
            columns={"year": "Year", "quantity_kg": "Quantity (kg)"}
        )
        st.bar_chart(by_year.set_index("Year"))


def render_gaps(plist, reg_df, master_df):
    st.caption(
        "Compared by chemical name only (strength and formulation ignored), so name spelling "
        "differences between sheets can show up here as gaps."
    )
    pl = add_keys(plist)
    active = add_keys(not_expired(reg_df))
    imp = add_keys(master_df)

    st.markdown("**Registered (active) but chemical not on the pesticide list**")
    off = active[~active["_name"].isin(set(pl["_name"]))]
    off_tbl = (
        off.groupby("common_name").agg(**{"Active registrations": ("reg_no", "nunique")})
        .reset_index().rename(columns={"common_name": "Chemical"})
        .sort_values("Active registrations", ascending=False)
    )
    st.caption(f"{len(off_tbl):,} chemicals")
    st.dataframe(off_tbl, hide_index=True)

    st.markdown("**Imported but chemical not on the pesticide list**")
    off_imp = imp[~imp["_name"].isin(set(pl["_name"]))]
    imp_tbl = (
        off_imp.groupby("common_name").agg(**{"Imported kg": ("quantity_kg", "sum")})
        .reset_index().rename(columns={"common_name": "Chemical"})
        .sort_values("Imported kg", ascending=False)
    )
    st.caption(f"{len(imp_tbl):,} chemicals")
    st.dataframe(imp_tbl, hide_index=True,
                 column_config={"Imported kg": st.column_config.NumberColumn(format="%,.0f")})

    st.markdown("**On the list but no active registration for the chemical**")
    unreg = pl[~pl["_name"].isin(set(active["_name"]))]
    unreg_tbl = (
        unreg.groupby("common_name").agg(Entries=("_prod", "count"), **{"Gazette volumes": ("royal_gazette_volume", lambda s: "; ".join(gazette_order(s)))})
        .reset_index().rename(columns={"common_name": "Chemical"})
    )
    st.caption(f"{len(unreg_tbl):,} chemicals")
    st.dataframe(unreg_tbl, hide_index=True)
