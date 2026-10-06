"""Pesticide list checks: look up a chemical or a combination (a+b, a+b+c)
against the official pesticide list (pesticide_list sheet), registrations
(reg_no) and imports (master_import).

Matching is on a normalized key (lower-case, all whitespace removed), so
"1-naphthylacetic acid" and "1-naphthylaceticacid" count as the same
chemical.
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


def render_summary(plist):
    c1, c2, c3 = st.columns(3)
    c1.metric("Entries on the list", f"{len(plist):,}")
    c2.metric("Distinct chemicals", f"{plist['common_name'].nunique():,}")
    c3.metric("Awaiting announcement", f"{(plist['royal_gazette_volume'] == AWAITING).sum():,}")
    counts = plist["royal_gazette_volume"].value_counts()
    counts = counts.reindex(gazette_order(counts.index))
    st.caption("Entries per Royal Gazette announcement")
    st.bar_chart(counts)



# ---------------------------------------------------------------------------
# Chemical / combination check
# ---------------------------------------------------------------------------
SOURCES = ["Pesticide list", "Registered", "Imported"]
CHECK_SOURCES = ["Registered", "Imported"]  # sheets the pesticide list can be checked against
_STRENGTH = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*%")
TOLERANCE = 1e-9
# technical-grade / reference-material labels, spelled several ways across the sheets
TECHNICAL_FORMS = {"TECH", "TC", "TK", "TECHNICAL CONCENTRATE", "ANALYTICAL STANDARD"}


def _unit(conc):
    m = re.search(r"W\s*/+\s*([VW])", conc, re.I)
    return f"W/{m.group(1).upper()}" if m else ""


def _form_label(f):
    f = re.sub(r"[\s.]+$", "", f.strip())
    return f.upper() if f else "UNSPECIFIED"


def combo_key(name):
    """Order-insensitive key for a '+' combination: 'b + a' == 'a+b'."""
    return "|".join(sorted(re.sub(r"\s+", "", p.lower()) for p in name.split("+") if p.strip()))


@st.cache_data
def build_pool(plist, reg_df, master_df):
    """One row per ingredient per distinct product, from all three sheets.
    '+'-separated names and strengths pair up by position; the unit (W/V or
    W/W) is written once and applies to every component. Entries whose
    strengths can't be read as 'number%' (e.g. cfu counts) are left out."""
    frames = [
        ("Pesticide list", plist, "royal_gazette_volume"),
        ("Registered", reg_df, None),
        ("Imported", master_df, None),
    ]
    rows = []
    for source, df, gz_col in frames:
        cols = ["common_name", "concentration", "formulation_type"] + ([gz_col] if gz_col else [])
        for rec in df[cols].drop_duplicates().itertuples(index=False):
            name, conc, form = rec[0], rec[1], rec[2]
            gazette = rec[3] if gz_col else ""
            names = [n.strip() for n in name.split("+")]
            concs = [c.strip() for c in conc.split("+")]
            nums = [_STRENGTH.match(c) for c in concs]
            if len(names) != len(concs) or any(n is None for n in nums):
                continue
            unit = _unit(conc)
            for n, m in zip(names, nums):
                rows.append((source, name, conc, _form_label(form), gazette, n, re.sub(r"\s+", "", n.lower()),
                             len(names), float(m.group(1)), unit, combo_key(name)))
    return pd.DataFrame(rows, columns=[
        "source", "entry", "concentration", "formulation", "gazette", "ingredient", "_ing",
        "n_components", "conc", "unit", "_combo",
    ])


ALL = "All"


@st.cache_data
def build_entries(plist):
    """Distinct chemical / concentration / formulation combinations on the
    pesticide list, used to fill the dropdowns."""
    cols = ["common_name", "concentration", "formulation_type"]
    e = plist[cols].drop_duplicates().copy()
    # ingredients in alphabetical order so a+b and b+a show up as one entry
    e["name"] = e["common_name"].map(
        lambda n: "+".join(sorted(re.sub(r"\s+", " ", p.lower()).strip() for p in n.split("+") if p.strip()))
    )
    e["_combo"] = e["common_name"].map(combo_key)
    e["_conc"] = _key(e["concentration"])
    e["form"] = e["formulation_type"].map(_form_label)
    return e


def _strength_sort(k):
    m = _STRENGTH.match(k)
    return (float(m.group(1)) if m else float("inf"), k)


def render_selectors(entries):
    """Chemical / concentration / formulation dropdowns, narrowed by each
    other. Leaving concentration and formulation on 'All' shows everything
    for the chemical. Returns (combo_key, display_name, conc_key, form) or
    None when no chemical is picked yet."""
    placeholder = "— Select —"
    first_name = entries.drop_duplicates("_combo").set_index("_combo")["name"]
    name_to_combo = {n: c for c, n in first_name.items()}
    names = [placeholder] + sorted(name_to_combo)

    if st.session_state.get("plist_name") not in names:
        st.session_state["plist_name"] = placeholder
    chem = st.selectbox(
        "Chemical (type to search; combinations are written a+b, ingredients in alphabetical order)",
        names, key="plist_name",
        help="Lists every chemical and combination on the pesticide list (pesticide_list sheet).",
    )
    # a new chemical resets the other two
    if st.session_state.get("plist_name_prev") != chem:
        st.session_state["plist_name_prev"] = chem
        st.session_state["plist_conc"] = ALL
        st.session_state["plist_form"] = ALL
    if chem == placeholder:
        return None

    combo = name_to_combo[chem]
    sub = entries[entries["_combo"] == combo]

    # sanitize stored picks against the options they'd now have, so a value
    # left over from another selection never crashes the widget
    conc_disp = sub.drop_duplicates("_conc").set_index("_conc")["concentration"].to_dict()
    form_sel = st.session_state.get("plist_form", ALL)
    conc_sub = sub if form_sel == ALL else sub[sub["form"] == form_sel]
    conc_opts = [ALL] + sorted(conc_sub["_conc"].unique(), key=_strength_sort)
    if st.session_state.get("plist_conc") not in conc_opts:
        st.session_state["plist_conc"] = ALL
    conc_sel = st.session_state["plist_conc"]
    form_sub = sub if conc_sel == ALL else sub[sub["_conc"] == conc_sel]
    form_opts = [ALL] + sorted(form_sub["form"].unique())
    if st.session_state.get("plist_form") not in form_opts:
        st.session_state["plist_form"] = ALL

    c1, c2 = st.columns(2)
    with c1:
        conc = st.selectbox("Concentration", conc_opts, key="plist_conc",
                            format_func=lambda k: ALL if k == ALL else conc_disp.get(k, k))
    with c2:
        form = st.selectbox("Formulation type", form_opts, key="plist_form")
    return combo, chem, conc, form


def alone_summary(pool, key):
    """Standalone (single-ingredient) strengths for one ingredient from every
    source, by formulation and unit, highest first."""
    solo = pool[(pool["_ing"] == key) & (pool["n_components"] == 1)]
    t = (solo.groupby(["source", "formulation", "unit"]).agg(**{"Max strength (%)": ("conc", "max"), "Entries": ("conc", "size")})
         .reset_index().sort_values("Max strength (%)", ascending=False))
    t["unit"] = t["unit"].replace("", "not stated")
    return t.rename(columns={"source": "Source", "formulation": "Formulation type", "unit": "Unit"})


def combination_check(pool, keys):
    """Pesticide-list entries that are exactly this combination, one row per
    ingredient, compared with that ingredient's strength on its own (from the
    pool: the list plus whichever other sheets are checked against): same
    formulation + unit, and the highest in any formulation (including
    technical grade)."""
    combo = "|".join(sorted(keys))
    entries = pool[
        (pool["_combo"] == combo) & (pool["n_components"] == len(keys)) & (pool["source"] == "Pesticide list")
    ].copy()
    if entries.empty:
        return entries
    solo = pool[pool["n_components"] == 1]
    same = solo.groupby(["_ing", "formulation", "unit"])["conc"].max().rename("alone_same")
    top = solo.sort_values("conc", ascending=False).drop_duplicates("_ing").set_index("_ing")
    entries = entries.join(same, on=["_ing", "formulation", "unit"])
    entries["alone_top"] = entries["_ing"].map(top["conc"])
    entries["top_where"] = entries["_ing"].map(top["formulation"] + " · " + top["source"])

    def verdict(c, ref):
        if pd.isna(ref):
            return "No standalone entry"
        if abs(c - ref) < TOLERANCE:
            return "Same"
        return "Lower" if c < ref else "Higher"

    entries["vs_same"] = [verdict(c, r) for c, r in zip(entries["conc"], entries["alone_same"])]
    entries["vs_top"] = [verdict(c, r) for c, r in zip(entries["conc"], entries["alone_top"])]
    entries["pct_top"] = (entries["conc"] / entries["alone_top"] * 100).round(1)
    return entries


def render_chemical_check(plist, reg_df, master_df):
    st.caption(
        "Pick a chemical (A) or a combination (A+B, A+B+C) from the pesticide list. You see its list entries, "
        "each ingredient on its own with its highest strength in any formulation (technical grade included), and "
        "whether the combination is lower than the ingredient alone. “Check against” brings in registrations and "
        "imports to compare the list with what is actually on the market."
    )
    c1, c2 = st.columns([3, 2])
    with c1:
        sources = st.multiselect(
            "Check the pesticide list against", CHECK_SOURCES, default=["Registered"], key="plist_sources",
            help="Registered = products in reg_no (what is sold in the market); Imported = master_import. "
                 "The pesticide list can contain chemicals that are never sold.",
        )
    with c2:
        active_only = st.checkbox("Only active (non-expired) registrations", value=True, key="plist_active")
    reg_used = not_expired(reg_df) if active_only else reg_df
    pool = build_pool(plist, reg_used, master_df)
    pool = pool[pool["source"].isin(["Pesticide list"] + sources)]
    entries = build_entries(plist)
    picked = render_selectors(entries)
    if picked is None:
        st.info("Pick a chemical or combination to check it. Concentration and formulation type are optional filters.")
        return
    combo, chem, conc_sel, form_sel = picked
    parts = [p.strip() for p in chem.split("+") if p.strip()]
    keys = list(dict.fromkeys(re.sub(r"\s+", "", p.lower()) for p in parts))
    names = {re.sub(r"\s+", "", p.lower()): p for p in parts}
    label = " + ".join(names[k] for k in keys)

    def narrow(df, conc_col, form_col, form_is_label=False):
        """Applies the concentration / formulation dropdown picks."""
        out = df
        if conc_sel != ALL:
            out = out[_key(out[conc_col]) == conc_sel]
        if form_sel != ALL:
            forms = out[form_col] if form_is_label else out[form_col].map(_form_label)
            out = out[forms == form_sel]
        return out

    # 1. the combination on the list
    st.subheader(label)
    pl = plist.copy()
    pl["_combo"] = pl["common_name"].map(combo_key)
    on_list = narrow(pl[pl["_combo"] == combo], "concentration", "formulation_type")
    st.markdown("**On the pesticide list**")
    regs_all = reg_used.copy()
    check_reg = "Registered" in sources
    regs_all["_prod"] = regs_all["common_name"].map(combo_key) + "|" + _key(regs_all["concentration"]) + "|" + regs_all["formulation_type"].map(_form_label)
    reg_counts = regs_all.groupby("_prod")["reg_no"].nunique()
    on_list = on_list.copy()
    on_list["Registered products"] = (
        on_list["common_name"].map(combo_key) + "|" + _key(on_list["concentration"]) + "|" + on_list["formulation_type"].map(_form_label)
    ).map(reg_counts).fillna(0).astype(int)
    show_cols = ["Chemical", "Concentration", "Formulation type", "Gazette volume"] + (["Registered products"] if check_reg else [])
    if on_list.empty:
        st.warning("No pesticide list entry for this " + ("combination" if len(keys) > 1 else "chemical")
                   + (" with the selected concentration / formulation." if (conc_sel != ALL or form_sel != ALL) else "."))
    else:
        st.dataframe(
            on_list.rename(columns={
                "common_name": "Chemical", "concentration": "Concentration",
                "formulation_type": "Formulation type", "royal_gazette_volume": "Gazette volume",
            })[show_cols],
            hide_index=True,
        )
        if check_reg:
            st.caption(
                "“Registered products” counts reg_no registrations with this exact chemical, strength and formulation"
                + (" (active only)" if active_only else "")
                + ". 0 means it is on the list but nothing is registered for it."
            )

    # 2. each ingredient alone
    st.markdown("**Each ingredient on its own**" if len(keys) > 1 else "**On its own**")
    st.caption(
        "Strengths of single-ingredient entries from: " + ", ".join(["Pesticide list"] + sources) + ". "
        "Technical grade and analytical standards appear here with their own (higher) strengths."
    )
    for k in keys:
        alone = alone_summary(pool, k)
        st.markdown(f"_{names[k]}_")
        if alone.empty:
            st.info(f"No single-ingredient entry for {names[k]} in " + ", ".join(["Pesticide list"] + sources) + ".")
            continue
        top = alone.iloc[0]
        formulated = alone[~alone["Formulation type"].isin(TECHNICAL_FORMS)]
        c1, c2 = st.columns(2)
        c1.metric("Highest alone (any formulation)", f"{top['Max strength (%)']:g}%",
                  f"{top['Formulation type']} · {top['Source']}", delta_color="off")
        if formulated.empty:
            c2.metric("Highest in a formulated product", "—")
        else:
            f = formulated.iloc[0]
            c2.metric("Highest in a formulated product", f"{f['Max strength (%)']:g}%",
                      f"{f['Formulation type']} · {f['Source']}", delta_color="off")
        st.dataframe(alone, hide_index=True)

    # 3. combination vs alone
    if len(keys) > 1:
        st.markdown("**Combination vs each ingredient alone**")
        res = combination_check(pool, keys)
        if not res.empty:
            res = narrow(res, "concentration", "formulation", form_is_label=True)
        if res.empty:
            st.info("No pesticide list entry with readable strengths for exactly this combination (and the selected concentration / formulation).")
        else:
            counts = res["vs_top"].value_counts()
            st.caption(
                f"{res.drop_duplicates(['source', 'entry', 'concentration', 'formulation']).shape[0]:,} "
                f"product(s); {counts.get('Lower', 0)} of {len(res)} ingredient strengths are lower than the "
                "highest standalone strength."
            )
            table = res.rename(columns={
                "source": "Source", "entry": "Combination", "concentration": "Concentration",
                "formulation": "Formulation type", "gazette": "Gazette volume", "ingredient": "Ingredient",
                "conc": "Strength in combination (%)", "unit": "Unit", "alone_same": "Alone, same formulation (%)",
                "alone_top": "Alone, highest (%)", "top_where": "Highest alone is in",
                "pct_top": "% of highest alone", "vs_same": "vs same formulation", "vs_top": "vs highest alone",
            })
            table["Unit"] = table["Unit"].replace("", "not stated")
            table = table[[
                "Combination", "Concentration", "Formulation type", "Gazette volume", "Ingredient",
                "Strength in combination (%)", "Unit", "Alone, same formulation (%)", "vs same formulation",
                "Alone, highest (%)", "Highest alone is in", "% of highest alone", "vs highest alone",
            ]].sort_values(["Combination", "Ingredient"])
            st.dataframe(table, hide_index=True)
            st.download_button(
                "⬇️ Download as CSV", table.to_csv(index=False).encode("utf-8-sig"),
                file_name="pesticide_combination_check.csv", mime="text/csv", key="plist_dl",
            )
            st.caption(
                "Rows are the pesticide list's own entries. “Same formulation” compares only with a single-ingredient entry of the same formulation type and "
                "unit (W/V or W/W). “Highest alone” compares with the highest strength in any formulation or "
                "unit, so it is the stricter test."
            )

    # 4. registrations + imports of this exact chemical/combination
    regs = reg_used.copy()
    regs["_combo"] = regs["common_name"].map(combo_key)
    regs = narrow(regs[regs["_combo"] == combo], "concentration", "formulation_type").copy()
    if check_reg:
        st.markdown("**Registered products**")
    if not check_reg:
        pass
    elif regs.empty:
        st.info("No registrations for this " + ("combination" if len(keys) > 1 else "chemical") + " in reg_no.")
    else:
        listed = {(_key(pd.Series([c])).iloc[0], _key(pd.Series([f])).iloc[0])
                  for c, f in zip(on_list["concentration"], on_list["formulation_type"])}
        regs["On list?"] = [
            "Yes" if (_key(pd.Series([c])).iloc[0], _key(pd.Series([f])).iloc[0]) in listed else "Strength/formulation not listed"
            for c, f in zip(regs["concentration"], regs["formulation_type"])
        ]
        expired = regs["expire"].notna() & (regs["expire"] < pd.Timestamp.today().normalize())
        regs["Active"] = (~expired).map({True: "Yes", False: "Expired"})
        cols = {
            "reg_no": "Reg. No.", "trade_name": "Trade name", "concentration": "Concentration",
            "formulation_type": "Formulation type", "distributor": "Distributor", "source": "Source",
            "issued": "Issued", "expire": "Expires", "Active": "Active", "On list?": "On list?",
        }
        st.caption(f"{len(regs):,} registration rows.")
        st.dataframe(regs.rename(columns=cols)[list(cols.values())].sort_values(["On list?", "Concentration"]), hide_index=True)

    imp = master_df.copy()
    imp["_combo"] = imp["common_name"].map(combo_key)
    imp = narrow(imp[imp["_combo"] == combo], "concentration", "formulation_type")
    if "Imported" in sources:
        st.markdown("**Imports**")
    if "Imported" not in sources:
        pass
    elif imp.empty:
        st.info("No imports recorded for this " + ("combination" if len(keys) > 1 else "chemical") + " in master_import.")
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
