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


def aggregate_metric(rows, label_col, metric):
    """Long table year x label x value for the chosen metric. Price uses
    aggregate_with_price, which ignores rows with no recorded value (2024 and
    2025 have none) instead of letting them drag the average down."""
    if metric == "price":
        agg = aggregate_with_price(rows, ["year", label_col])
        return agg.rename(columns={"price_thb": "value"})[["year", label_col, "value"]]
    return rows.groupby(["year", label_col], as_index=False)[metric].sum().rename(columns={metric: "value"})


def render_result(rows, label_col, metric_name, key):
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

    order = list(pivot.index)
    shown = order[:MAX_LINES]
    if len(order) > MAX_LINES:
        st.caption(f"Chart shows the {MAX_LINES} largest of {len(order)} lines; the table lists all of them.")
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
# 1. Specific products
# ---------------------------------------------------------------------------
def render_product_aggregation(df):
    """Pick exact chemical + concentration + formulation products, then sum."""
    products = df[["common_name", "concentration", "formulation_type"]].drop_duplicates().copy()
    products["label"] = _label_product(products)
    all_labels = sorted(products["label"])

    st.caption(
        "Find chemicals with the filter, then pick the exact products you want — a chemical, its strength "
        "and its formulation — across as many chemicals as you like."
    )
    f1, f2 = st.columns([3, 2])
    with f1:
        query = st.text_input("Filter products", key="agg_prod_filter",
                              placeholder="e.g. abamectin, copper sulfate, 1.8%, EC",
                              help="Whole-word match on the product text (chemical, strength, formulation).")
    with f2:
        partial = st.checkbox("Match part of a word", key="agg_prod_partial")
    shown = filter_names(all_labels, query, partial)

    selected = [p for p in st.session_state.get("agg_products", []) if p in set(all_labels)]
    st.session_state["agg_products"] = selected  # drop picks that no longer exist
    options = sorted(set(shown) | set(selected))

    def add_all_shown():
        cur = st.session_state.get("agg_products", [])
        st.session_state["agg_products"] = sorted(set(cur) | set(shown))

    b1, b2 = st.columns([1, 4])
    with b1:
        st.button(f"Add all {len(shown):,} shown", on_click=add_all_shown, disabled=not (0 < len(shown) <= 60),
                  help="Available when 60 products or fewer match the filter.", key="agg_add_all")
    with b2:
        st.caption(f"{len(shown):,} of {len(all_labels):,} products match the filter; {len(selected)} picked.")
    st.multiselect("Products", options, key="agg_products", placeholder="Pick one or more products")

    picked = st.session_state.get("agg_products", [])
    if not picked:
        st.info("Pick one or more products above to sum their imports by year.")
        return

    c1, c2 = st.columns(2)
    with c1:
        mode = st.radio(
            "Show", ["By chemical", "Each product", "All picked as one total"], key="agg_prod_mode", horizontal=True,
            help="By chemical adds up the picked strengths and formulations of each chemical into one line.",
        )
    with c2:
        metric_name = st.selectbox("Measure", list(METRICS), key="agg_prod_metric")

    rows = df.assign(_label=_label_product(df))
    rows = rows[rows["_label"].isin(picked)].copy()
    if mode == "By chemical":
        rows["_group"] = rows["common_name"]
    elif mode == "Each product":
        rows["_group"] = rows["_label"]
    else:
        rows["_group"] = f"{len(picked)} picked products"
    render_result(rows, "_group", metric_name, "agg_products_result")


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

    codes_by_volume = (rows.groupby(label_col)["quantity_kg"].sum().sort_values(ascending=False))
    codes_key = f"agg_codes_{system}_{label_col}"
    valid = set(codes_by_volume.index)
    if codes_key in st.session_state:  # drop picks that no longer exist (e.g. after toggling mixtures)
        st.session_state[codes_key] = [c for c in st.session_state[codes_key] if c in valid]
    picks = st.multiselect(
        f"{system} codes (leave empty for all)", list(codes_by_volume.index), key=codes_key,
        help="Ordered by import volume. Typing searches the list.",
    )
    show = st.radio("Show", ["Each separately", "Combined into one total", "Each + combined total"],
                    key="agg_show", horizontal=True)

    chosen = picks or list(codes_by_volume.index)
    sel = rows[rows[label_col].isin(chosen)]
    parts = []
    if show in ("Each separately", "Each + combined total"):
        parts.append(sel.assign(_group=sel[label_col]))
    if show in ("Combined into one total", "Each + combined total"):
        combined = sel.drop_duplicates("_row")  # a product in several chosen codes counts once
        name = f"All {len(chosen)} codes combined" if not picks else f"Combined: {len(chosen)} selected"
        parts.append(combined.assign(_group=name))
    render_result(pd.concat(parts, ignore_index=True), "_group", metric_name, f"agg_{system.lower()}_result")

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
