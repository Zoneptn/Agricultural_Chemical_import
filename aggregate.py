"""Import aggregation for the Market Summary page, beyond typing a keyword:

  1. Specific products - pick exact chemical + concentration + formulation
     combinations (across several chemicals) and sum them by year.
  2. Mode-of-action groups - sum imports by IRAC / HRAC / FRAC code (or its
     main group, or chemical group), with several codes selectable and
     combinable into one total.

Both work on master_import rows. A row is one product-year-origin shipment.
"""
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from common import aggregate_with_price, filter_names

METRICS = {
    "Quantity (kg)": "quantity_kg",
    "Active ingredient (kg)": "ai_kg",
    "Value (THB)": "value_bht",
    "Avg price (THB/kg)": "price",
}
MAX_LINES = 10


def _label_product(df):
    return df["common_name"] + " · " + df["concentration"] + " · " + df["formulation_type"]


def natural_key(label):
    """Sort key for a code label like '10A — Nicotinic …' or '4 · Group':
    numbers in numeric order (1, 1A, 1B, 2, … 10, 11, 12/32, 16.1), then
    letter codes (M1, NC, UN) after them."""
    code = re.split(r" — | · ", str(label))[0]
    tokens = re.findall(r"\d+(?:\.\d+)?|[A-Za-z]+", code) or [code]
    return [(0, float(t), "") if t[0].isdigit() else (1, 0.0, t.upper()) for t in tokens]


def aggregate_metric(rows, label_col, metric):
    """Long table year x label x value for the chosen metric. Price uses
    aggregate_with_price, which ignores rows with no recorded value (2024 and
    2025 have none) instead of letting them drag the average down."""
    if metric == "price":
        agg = aggregate_with_price(rows, ["year", label_col])
        return agg.rename(columns={"price_thb": "value"})[["year", label_col, "value"]]
    return rows.groupby(["year", label_col], as_index=False)[metric].sum().rename(columns={metric: "value"})


def render_result(rows, label_col, metric_name, key, order_key=None):
    """Chart + year-by-year table + CSV for rows that already carry a label
    column. `rows` may repeat a master_import row under several labels (a
    mixture counted under each of its codes)."""
    metric = METRICS[metric_name]
    long = aggregate_metric(rows, label_col, metric)
    if long.empty:
        st.info("No imports for this selection.")
        return
    fmt = "{:,.2f}" if metric == "price" else "{:,.0f}"

    pivot = long.pivot(index=label_col, columns="year", values="value")
    if metric == "price":
        total = aggregate_with_price(rows, [label_col]).set_index(label_col)["price_thb"]
    else:
        total = pivot.sum(axis=1, min_count=1)
    pivot["Total"] = total
    pivot = pivot.sort_values("Total", ascending=False)
    pivot.columns = [str(c) for c in pivot.columns]

    by_volume = list(pivot.index)
    shown = by_volume[:MAX_LINES]
    if len(by_volume) > MAX_LINES:
        st.caption(f"Chart shows the {MAX_LINES} largest of {len(by_volume)} lines; the table lists all of them.")
    if order_key:  # e.g. code order for IRAC / HRAC / FRAC: table and chart legend follow it
        pivot = pivot.loc[sorted(pivot.index, key=order_key)]
        shown = sorted(shown, key=order_key)
    fig = px.line(
        long[long[label_col].isin(shown)], x="year", y="value", color=label_col, markers=True,
        category_orders={label_col: shown}, labels={"value": metric_name, "year": "Year", label_col: ""},
    )
    fig.update_layout(legend=dict(orientation="h", y=-0.25), margin=dict(t=10))
    fig.update_xaxes(dtick=1)
    st.plotly_chart(fig, width="stretch", key=f"{key}_chart")

    table = pivot.reset_index().rename(columns={label_col: "Group"})
    st.dataframe(table.style.format({c: fmt for c in table.columns if c != "Group"}, na_rep="—"), hide_index=True)
    st.download_button(
        "⬇️ Download as CSV", table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{key}.csv", mime="text/csv", key=f"{key}_dl",
    )


# ---------------------------------------------------------------------------
# 1. Specific products: up to 25 rows of chemical / concentration / formulation
# ---------------------------------------------------------------------------
MAX_ROWS = 25
PLACEHOLDER = "— Select —"
ANY = "All"


def _strength_key(k):
    m = re.match(r"\s*(\d+(?:\.\d+)?)", k)
    return (float(m.group(1)) if m else float("inf"), k)


def render_product_aggregation(df):
    """Up to 25 rows, each a chemical + concentration + formulation type
    chosen from dropdowns (concentration and formulation narrow to what that
    chemical actually has; 'All' leaves one open), summed by year."""
    combos = df[["common_name", "concentration", "formulation_type"]].drop_duplicates()
    all_names = sorted(combos["common_name"].unique())
    name_set = set(all_names)

    st.caption(
        f"Build a list of up to {MAX_ROWS} products. For each row pick a chemical, then optionally a "
        "concentration and a formulation type (leave them on “All” to include every strength or formulation "
        "of that chemical). The rows are added together."
    )
    t1, t2, t3 = st.columns([1, 3, 2])
    with t1:
        n_rows = st.number_input("Rows", min_value=1, max_value=MAX_ROWS, value=5, step=1, key="agg_nrows")
    with t2:
        query = st.text_input(
            "Filter the chemical lists", key="agg_prod_filter", placeholder="e.g. abamectin, copper sulfate",
            help="Whole-word match; narrows the chemical dropdown in every row. "
                 "A row keeps its chemical even if the filter would hide it.",
        )
    with t3:
        partial = st.checkbox("Match part of a word", key="agg_prod_partial")
    matches = set(filter_names(all_names, query, partial))

    heads = st.columns([3, 2, 2])
    specs = []
    for i in range(int(n_rows)):
        kc, kk, kf, kp = (f"agg_r{i}_{x}" for x in ("chem", "conc", "form", "prev"))

        # --- sanitize this row's stored picks before its widgets exist ---
        chem = st.session_state.get(kc, PLACEHOLDER)
        if chem != PLACEHOLDER and chem not in name_set:
            chem = st.session_state[kc] = PLACEHOLDER
        if st.session_state.get(kp) != chem:           # new chemical: reset strength / formulation
            st.session_state[kp] = chem
            st.session_state[kk] = ANY
            st.session_state[kf] = ANY
        sub = combos[combos["common_name"] == chem] if chem != PLACEHOLDER else combos.iloc[0:0]
        form_sel = st.session_state.get(kf, ANY)
        conc_sub = sub if form_sel == ANY else sub[sub["formulation_type"] == form_sel]
        conc_opts = [ANY] + sorted(conc_sub["concentration"].unique(), key=_strength_key)
        if st.session_state.get(kk) not in conc_opts:
            st.session_state[kk] = ANY
        conc_sel = st.session_state[kk]
        form_sub = sub if conc_sel == ANY else sub[sub["concentration"] == conc_sel]
        form_opts = [ANY] + sorted(form_sub["formulation_type"].unique())
        if st.session_state.get(kf) not in form_opts:
            st.session_state[kf] = ANY

        chem_opts = [PLACEHOLDER] + sorted(matches | ({chem} if chem != PLACEHOLDER else set()))
        cols = st.columns([3, 2, 2])
        first = i == 0
        vis = "visible" if first else "collapsed"
        with cols[0]:
            chem = st.selectbox(f"Chemical name (row {i + 1})" if not first else "Chemical name", chem_opts,
                                key=kc, label_visibility=vis)
        with cols[1]:
            conc = st.selectbox(f"Concentration (row {i + 1})" if not first else "Concentration", conc_opts,
                                key=kk, label_visibility=vis, disabled=chem == PLACEHOLDER)
        with cols[2]:
            form = st.selectbox(f"Formulation type (row {i + 1})" if not first else "Formulation type", form_opts,
                                key=kf, label_visibility=vis, disabled=chem == PLACEHOLDER)
        if chem != PLACEHOLDER:
            spec = (chem, conc, form)
            if spec not in specs:
                specs.append(spec)

    if not specs:
        st.info("Pick a chemical in at least one row to sum its imports by year.")
        return

    c1, c2 = st.columns([3, 2])
    with c1:
        mode = st.radio(
            "Show", ["One total", "Each row", "By chemical", "Each row + total"], key="agg_prod_mode", horizontal=True,
            help="One total adds all rows together. By chemical adds up the rows of each chemical.",
        )
    with c2:
        metric_name = st.selectbox("Measure", list(METRICS), key="agg_prod_metric")

    def label(spec):
        chem, conc, form = spec
        return " · ".join([chem, "all strengths" if conc == ANY else conc, "all formulations" if form == ANY else form])

    rows_df = df.reset_index().rename(columns={"index": "_row"})
    per_spec = []
    for spec in specs:
        chem, conc, form = spec
        m = rows_df["common_name"] == chem
        if conc != ANY:
            m &= rows_df["concentration"] == conc
        if form != ANY:
            m &= rows_df["formulation_type"] == form
        per_spec.append(rows_df[m].assign(_group=label(spec)))
    union = pd.concat(per_spec).drop_duplicates("_row")  # a shipment matched by two rows counts once

    parts = []
    if mode in ("Each row", "Each row + total"):
        parts.append(pd.concat(per_spec))
    if mode in ("One total", "Each row + total"):
        parts.append(union.assign(_group=f"Total of {len(specs)} selected product{'s' if len(specs) != 1 else ''}"))
    if mode == "By chemical":
        parts.append(union.assign(_group=union["common_name"]))

    st.caption(f"{len(union):,} shipments matched across {len(specs)} row{'s' if len(specs) != 1 else ''}.")
    if sum(len(p) for p in per_spec) > len(union) and mode in ("Each row", "Each row + total"):
        st.caption("Some rows overlap (for example “All” strengths plus one specific strength of the same chemical), "
                   "so separate rows can add up to more than the total, which counts each shipment once.")
    render_result(pd.concat(parts, ignore_index=True), "_group", metric_name, "agg_products_result")


# ---------------------------------------------------------------------------
# 2. IRAC / HRAC / FRAC groups
# ---------------------------------------------------------------------------
SYSTEM_CATEGORIES = {  # which master_import categories each system is meant to cover
    "IRAC": ["insecticide", "acaricide"],
    "HRAC": ["herbicide"],
    "FRAC": ["fungicide"],
}
SYSTEM_BLURB = {
    "IRAC": "insecticide / acaricide mode of action",
    "HRAC": "herbicide mode of action",
    "FRAC": "fungicide mode of action",
}
MIN_PREFIX = 5


def _norm(s):
    return re.sub(r"[\s\-]+", "", str(s).lower())


def _english(text):
    """The English part of a mixed Thai/English mode-of-action text."""
    for t in reversed(re.findall(r"\(([^()]*)\)", str(text))):
        if re.search(r"[A-Za-z]{3}", t):
            return t.strip()
    return re.sub(r"\s+", " ", str(text)).strip()


def _code(v):
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def class_table(tables, system):
    """One row per (active ingredient, code, chemical group) for a system."""
    t = tables[system]
    group_col = "chemical_class" if system == "IRAC" else "chemical_group"
    out = pd.DataFrame({
        "_n": t["common_name"].map(_norm),
        "code": t["code"].map(_code),
        "group": t[group_col].fillna("").astype(str).str.strip(),
        "moa": t["mode_of_action"].map(_english),
    })
    out = out[(out["_n"] != "") & (out["code"] != "")]
    out["main"] = out["code"].str.extract(r"^(\d+)", expand=False).fillna(out["code"])
    moa_by_code = out.groupby("code")["moa"].agg(lambda s: s.value_counts().index[0])
    out["label_code"] = out["code"] + " — " + out["code"].map(moa_by_code)
    first_in_main = out.groupby("main")["code"].agg(lambda s: sorted(s.unique())[0])
    out["label_main"] = out["main"] + " — " + out["main"].map(first_in_main).map(moa_by_code)
    out["label_group"] = out["code"] + " · " + out["group"].where(out["group"] != "", "(no chemical group)")
    return out.drop_duplicates(["_n", "code", "group"]).reset_index(drop=True)


@st.cache_data
def map_products(names, tables, system):
    """Maps each master_import chemical name to class rows. Each '+' component
    is matched by normalized name; failing that, by the longest class name it
    starts with (so salt/ester forms like 'glyphosate-isopropylammonium' or
    'paraquat dichloride' find 'glyphosate' / 'paraquat'). Returns one row per
    (product name, component, class row) with how it matched."""
    cls = class_table(dict(tables), system)
    exact = {n: g for n, g in cls.groupby("_n")}
    by_len = sorted(exact, key=len, reverse=True)
    rows = []
    for name in names:
        comps = [c.strip() for c in str(name).split("+") if c.strip()]
        for comp in comps:
            cn = _norm(comp)
            kind, hit = None, None
            if cn in exact:
                kind, hit = "exact", cn
            else:
                for cand in by_len:
                    if len(cand) >= MIN_PREFIX and cn.startswith(cand):
                        kind, hit = "parent chemical", cand
                        break
            if hit is None:
                continue
            g = exact[hit].copy()
            g["common_name"], g["component"], g["match"], g["class_name"] = name, comp, kind, hit
            g["n_components"] = len(comps)
            rows.append(g)
    if not rows:
        return pd.DataFrame(columns=list(cls.columns) + ["common_name", "component", "match", "class_name", "n_components"])
    return pd.concat(rows, ignore_index=True)


LEVELS = {"Code": "label_code", "Chemical group within code": "label_group"}


def render_group_aggregation(df, tables):
    st.caption(
        "Sum imports by mode-of-action code. Pick the system, the level, and any number of codes; "
        "show them separately, combined into one total, or both."
    )
    c1, c2, c3 = st.columns([2, 3, 2])
    with c1:
        system = st.radio("System", list(SYSTEM_CATEGORIES), key="agg_system", horizontal=True,
                          format_func=lambda s: f"{s}", help=", ".join(f"{k}: {v}" for k, v in SYSTEM_BLURB.items()))
    levels = dict(LEVELS)
    if system == "IRAC":
        levels = {"Main group (1A + 1B → 1)": "label_main", **levels}
    with c2:
        level_name = st.radio("Level", list(levels), key=f"agg_level_{system}", horizontal=True)
    with c3:
        metric_name = st.selectbox("Measure", list(METRICS), key="agg_grp_metric")
    label_col = levels[level_name]
    include_mixtures = st.checkbox(
        "Include mixtures (a product counts under the code of every ingredient it contains)",
        value=True, key="agg_mixtures",
    )

    names = tuple(sorted(df["common_name"].unique()))
    mapping = map_products(names, tuple(sorted(tables.items())), system)
    if not include_mixtures:
        mapping = mapping[mapping["n_components"] == 1]

    # master_import rows (kept by index so a row is counted once in a combined total)
    rows = df.reset_index().rename(columns={"index": "_row"}).merge(
        mapping[["common_name", label_col, "match"]].drop_duplicates(), on="common_name", how="inner"
    )

    # coverage against the categories this system is meant for
    cat = df[df["category"].isin(SYSTEM_CATEGORIES[system])]
    covered = cat[cat["common_name"].isin(set(mapping["common_name"]))]
    cat_qty = cat["quantity_kg"].sum()
    if cat_qty:
        st.caption(
            f"{system} codes cover {covered['quantity_kg'].sum() / cat_qty:.1%} of "
            f"{' / '.join(SYSTEM_CATEGORIES[system])} import volume (by quantity). The rest has no match in the "
            f"{system} sheet by name."
        )
    if rows.empty:
        st.info(f"No imports matched to {system} codes.")
        return

    codes_by_volume = rows.groupby(label_col)["quantity_kg"].sum()
    code_order = sorted(codes_by_volume.index, key=natural_key)
    codes_key = f"agg_codes_{system}_{label_col}"
    valid = set(codes_by_volume.index)
    if codes_key in st.session_state:  # drop picks that no longer exist (e.g. after toggling mixtures)
        st.session_state[codes_key] = [c for c in st.session_state[codes_key] if c in valid]
    picks = st.multiselect(
        f"{system} codes (leave empty for all)", code_order, key=codes_key,
        help="Listed in code order (1, 1A, 1B, 2 … 10, 11; letter codes last). Typing searches the list.",
    )
    show = st.radio("Show", ["Each separately", "Combined into one total", "Each + combined total"],
                    key="agg_show", horizontal=True)

    chosen = picks or code_order
    sel = rows[rows[label_col].isin(chosen)]
    parts = []
    if show in ("Each separately", "Each + combined total"):
        parts.append(sel.assign(_group=sel[label_col]))
    if show in ("Combined into one total", "Each + combined total"):
        combined = sel.drop_duplicates("_row")  # a product in several chosen codes counts once
        name = f"All {len(chosen)} codes combined" if not picks else f"Combined: {len(chosen)} selected"
        parts.append(combined.assign(_group=name))
    combined_names = set(pd.concat(parts)["_group"]) - set(chosen)  # the combined-total line goes first

    def order_key(g):
        return (0, []) if g in combined_names else (1, natural_key(g))

    render_result(pd.concat(parts, ignore_index=True), "_group", metric_name, f"agg_{system.lower()}_result",
                  order_key=order_key)

    if len(picks) > 1 or show != "Each separately":
        st.caption(
            "A mixture belongs to several codes, so separate lines can add up to more than the combined total, "
            "which counts each product once."
        )

    uncls = cat[~cat["common_name"].isin(set(mapping["common_name"]))]
    with st.expander(f"Not classified in {system} ({uncls['common_name'].nunique():,} names)"):
        if uncls.empty:
            st.write("Everything in these categories is classified.")
        else:
            top = (uncls.groupby("common_name")["quantity_kg"].sum().sort_values(ascending=False)
                   .head(25).reset_index().rename(columns={"common_name": "Chemical", "quantity_kg": "Quantity (kg)"}))
            st.dataframe(top.style.format({"Quantity (kg)": "{:,.0f}"}), hide_index=True)
            st.caption("Top 25 by quantity. Add these names to the sheet (or fix the spelling) to include them.")
    with st.expander("Names matched through their parent chemical"):
        partial = mapping[mapping["match"] == "parent chemical"][["common_name", "component", "class_name"]]
        partial = partial.drop_duplicates().rename(columns={
            "common_name": "Import name", "component": "Ingredient", "class_name": "Matched to (sheet name)",
        })
        if partial.empty:
            st.write("None.")
        else:
            st.dataframe(partial, hide_index=True)
            st.caption("Salt / ester names matched to the parent chemical in the sheet by their starting letters.")
