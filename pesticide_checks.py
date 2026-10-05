"""Pesticide list checks: look up a chemical or a combination (a+b, a+b+c)
against the official pesticide list (pesticide_list sheet), registrations
(reg_no) and imports (master_import).

Matching is on a normalized key (lower-case, all whitespace removed), so
"1-naphthylacetic acid" and "1-naphthylaceticacid" count as the same
chemical.
"""
import difflib
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


def resolve_input(text, pool):
    """Splits 'a+b+c' into ingredient keys. Returns (keys, unknown) where
    unknown maps each unrecognised piece to close-match suggestions."""
    known = pool.drop_duplicates("_ing").set_index("_ing")["ingredient"]
    keys, unknown = [], {}
    for piece in [p for p in text.split("+") if p.strip()]:
        k = re.sub(r"\s+", "", piece.lower())
        if k in known.index:
            if k not in keys:
                keys.append(k)
        else:
            near = difflib.get_close_matches(k, list(known.index), n=4, cutoff=0.7)
            near += [x for x in known.index if k in x and x not in near][:4]
            unknown[piece.strip()] = [known[x] for x in near[:5]]
    return keys, unknown


def alone_summary(pool, key):
    """Standalone (single-ingredient) strengths for one ingredient from every
    source, by formulation and unit, highest first."""
    solo = pool[(pool["_ing"] == key) & (pool["n_components"] == 1)]
    t = (solo.groupby(["source", "formulation", "unit"]).agg(**{"Max strength (%)": ("conc", "max"), "Entries": ("conc", "size")})
         .reset_index().sort_values("Max strength (%)", ascending=False))
    t["unit"] = t["unit"].replace("", "not stated")
    return t.rename(columns={"source": "Source", "formulation": "Formulation type", "unit": "Unit"})


def combination_check(pool, keys):
    """Entries that are exactly this combination, one row per ingredient,
    compared with that ingredient's strength on its own: same formulation +
    unit, and the highest in any formulation (including technical grade)."""
    combo = "|".join(sorted(keys))
    entries = pool[(pool["_combo"] == combo) & (pool["n_components"] == len(keys))].copy()
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
        "Type one chemical (A) or a combination (A+B, A+B+C). For a combination you get each ingredient on its "
        "own with its highest strength in any formulation, including technical grade, and whether the combination "
        "is lower than the ingredient alone."
    )
    pool = build_pool(plist, reg_df, master_df)
    text = st.text_input(
        "Chemical or combination", placeholder="e.g. abamectin, or abamectin+emamectin benzoate", key="plist_query"
    )
    if not text.strip():
        st.info("Type a chemical or a combination such as A+B to check it.")
        return
    keys, unknown = resolve_input(text, pool)
    for piece, near in unknown.items():
        msg = f"“{piece}” isn't a chemical name found in the list, registrations or imports."
        st.warning(msg + (f" Did you mean: {', '.join(near)}?" if near else ""))
    if unknown or not keys:
        return

    names = pool.drop_duplicates("_ing").set_index("_ing")["ingredient"]
    label = " + ".join(names[k] for k in keys)

    # 1. the combination on the list
    st.subheader(label)
    combo = "|".join(sorted(keys))
    pl = plist.copy()
    pl["_combo"] = pl["common_name"].map(combo_key)
    on_list = pl[pl["_combo"] == combo]
    st.markdown("**On the pesticide list**")
    if on_list.empty:
        st.warning("This exact " + ("combination" if len(keys) > 1 else "chemical") + " is not an entry on the pesticide list.")
    else:
        st.dataframe(
            on_list.rename(columns={
                "common_name": "Chemical", "concentration": "Concentration",
                "formulation_type": "Formulation type", "royal_gazette_volume": "Gazette volume",
            })[["Chemical", "Concentration", "Formulation type", "Gazette volume"]],
            hide_index=True,
        )

    # 2. each ingredient alone
    st.markdown("**Each ingredient on its own**" if len(keys) > 1 else "**On its own**")
    st.caption(
        "Strengths of single-ingredient entries from the pesticide list, registrations and imports. "
        "Technical grade and analytical standards appear here with their own (higher) strengths."
    )
    for k in keys:
        alone = alone_summary(pool, k)
        st.markdown(f"_{names[k]}_")
        if alone.empty:
            st.info(f"No single-ingredient entry for {names[k]} in the list, registrations or imports.")
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
        if res.empty:
            st.info("No entry for exactly this combination in the pesticide list, registrations or imports.")
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
                "Source", "Combination", "Concentration", "Formulation type", "Gazette volume", "Ingredient",
                "Strength in combination (%)", "Unit", "Alone, same formulation (%)", "vs same formulation",
                "Alone, highest (%)", "Highest alone is in", "% of highest alone", "vs highest alone",
            ]].sort_values(["Source", "Combination", "Ingredient"])
            st.dataframe(table, hide_index=True)
            st.download_button(
                "⬇️ Download as CSV", table.to_csv(index=False).encode("utf-8-sig"),
                file_name="pesticide_combination_check.csv", mime="text/csv", key="plist_dl",
            )
            st.caption(
                "“Same formulation” compares only with a single-ingredient entry of the same formulation type and "
                "unit (W/V or W/W). “Highest alone” compares with the highest strength in any formulation or "
                "unit, so it is the stricter test."
            )

    # 4. registrations + imports of this exact chemical/combination
    regs = reg_df.copy()
    regs["_combo"] = regs["common_name"].map(combo_key)
    regs = regs[regs["_combo"] == combo].copy()
    st.markdown("**Registered products**")
    if regs.empty:
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
    imp = imp[imp["_combo"] == combo]
    st.markdown("**Imports**")
    if imp.empty:
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
