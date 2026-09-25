"""Market-summary logic: category trend, origin-country market share, and
year-over-year mover analysis, all built from master_import.

master_import has no category field, so category is derived by mapping each
common_name to the category most often recorded for it in reg_no. Coverage
isn't total — chemicals reg_no doesn't recognize (salt/ester variants,
mixtures, names absent from reg_no) fall under "Uncategorized" rather than
being silently dropped, so totals stay honest.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

UNCATEGORIZED = "Uncategorized"


@st.cache_data
def build_category_map(reg_df):
    """common_name -> its most-common category in reg_no (mode; ties take the
    first alphabetically for determinism)."""
    return reg_df.groupby("common_name")["category"].agg(lambda s: sorted(s.mode())[0])


def with_category(df, category_map):
    out = df.copy()
    out["category"] = out["common_name"].map(category_map).fillna(UNCATEGORIZED)
    return out


def render_keyword_aggregation(df, reg_df):
    """Sums import quantity/price by year across every chemical whose name
    contains a typed keyword — e.g. "copper" rolls up copper hydroxide,
    copper oxychloride, copper sulfate, etc. into one trend, since these are
    usually different formulations of the same underlying active ingredient
    family rather than genuinely separate products.

    Accepts several comma-separated keywords so different families can be
    compared directly on the same charts (e.g. "copper, mancozeb, sulfur")."""
    raw = st.text_input(
        "Aggregate by keyword(s) in chemical name — separate several with commas",
        placeholder="e.g. copper, mancozeb, sulfur",
    )

    if not raw or not raw.strip():
        st.info(
            "Type one or more keywords above — e.g. \"copper\" or \"copper, mancozeb\" — to sum up "
            "each matching family's import volume by year and compare them."
        )
        return

    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    groups = {}
    empty_keywords = []
    for kw in keywords:
        matched = df[df["common_name"].str.lower().str.contains(kw.lower(), na=False, regex=False)]
        if matched.empty:
            empty_keywords.append(kw)
        else:
            groups[kw] = matched

    if empty_keywords:
        st.warning(f"No chemical names contain: {', '.join(empty_keywords)}.")
    if not groups:
        return

    active_reg_df = reg_df[reg_df["expire"].isna() | (reg_df["expire"] >= pd.Timestamp.now().normalize())]

    # ---- Summary comparison table, one row per keyword ----
    summary_rows = []
    for kw, matched in groups.items():
        names = matched["common_name"].unique()
        regs = active_reg_df[active_reg_df["common_name"].str.lower().isin([n.lower() for n in names])]
        total_qty = matched["quantity_kg"].sum()
        total_val = matched["value_bht"].sum()
        summary_rows.append({
            "Keyword": kw,
            "Matched products": len(names),
            "Total quantity (kg)": total_qty,
            "Total value (THB)": total_val,
            "Avg price (THB/kg)": total_val / total_qty if total_qty else 0,
            "Active registrations": len(regs),
            "Distributors": regs["distributor"].nunique(),
        })
    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(
        summary_df.style.format({
            "Total quantity (kg)": "{:,.0f}",
            "Total value (THB)": "{:,.0f}",
            "Avg price (THB/kg)": "{:,.2f}",
        }),
        width='stretch', hide_index=True,
    )

    # ---- Combined trend, one line per keyword ----
    combined = pd.concat([matched.assign(keyword=kw) for kw, matched in groups.items()], ignore_index=True)
    by_year = combined.groupby(["year", "keyword"], as_index=False)[["quantity_kg", "value_bht"]].sum()
    by_year["price_thb"] = by_year["value_bht"] / by_year["quantity_kg"].replace(0, pd.NA)

    st.markdown("**Import quantity (kg) by year**")
    fig_qty = px.line(
        by_year, x="year", y="quantity_kg", color="keyword", markers=True,
        labels={"year": "Year", "quantity_kg": "Import quantity (kg)", "keyword": "Keyword"},
    )
    st.plotly_chart(fig_qty, width='stretch')

    st.markdown("**Average price (THB/kg) by year**")
    fig_price = px.line(
        by_year, x="year", y="price_thb", color="keyword", markers=True,
        labels={"year": "Year", "price_thb": "Average price (THB/kg)", "keyword": "Keyword"},
    )
    st.plotly_chart(fig_price, width='stretch')

    # ---- Origin breakdown: top supplying countries per keyword ----
    st.markdown("**Top origin countries per keyword**")
    by_origin = combined.groupby(["keyword", "origin"], as_index=False)["quantity_kg"].sum()
    top_per_keyword = (
        by_origin.sort_values("quantity_kg", ascending=False)
        .groupby("keyword", group_keys=False)
        .head(6)
    )
    fig_origin = px.bar(
        top_per_keyword, x="quantity_kg", y="origin", color="keyword", orientation="h", barmode="group",
        labels={"quantity_kg": "Import quantity (kg)", "origin": "Origin", "keyword": "Keyword"},
    )
    fig_origin.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_origin, width='stretch')

    # ---- Breakdown by exact matched chemical name, per keyword ----
    with st.expander("Breakdown by matched chemical name"):
        for kw, matched in groups.items():
            st.markdown(f"**\"{kw}\"**")
            by_name = matched.groupby("common_name", as_index=False)["quantity_kg"].sum().sort_values(
                "quantity_kg", ascending=False
            )
            by_name = by_name.rename(columns={"common_name": "Chemical", "quantity_kg": "Total quantity (kg)"})
            st.dataframe(by_name.style.format({"Total quantity (kg)": "{:,.0f}"}), width='stretch', hide_index=True)


def render_category_trend(df, sel_categories):
    """Total import quantity by year, one line per category — all categories
    shown by default, narrow via sel_categories to fewer."""
    view = df[df["category"].isin(sel_categories)] if sel_categories else df
    trend = view.groupby(["year", "category"], as_index=False)["quantity_kg"].sum()

    fig = px.line(
        trend, x="year", y="quantity_kg", color="category", markers=True,
        labels={"year": "Year", "quantity_kg": "Import quantity (kg)", "category": "Category"},
    )
    st.plotly_chart(fig, width='stretch')

    uncategorized_share = df[df["category"] == UNCATEGORIZED]["quantity_kg"].sum() / df["quantity_kg"].sum()
    st.caption(
        f"Category is derived from reg_no by chemical name; about {uncategorized_share:.0%} of import "
        f"volume comes from chemical name variants reg_no doesn't recognize and falls under \"{UNCATEGORIZED}\"."
    )


def render_origin_market_share(df, top_n=8):
    """100%-stacked bar of import-quantity market share by origin country,
    one bar per year — shows both the year-over-year comparison and the
    share breakdown in a single chart. The same top-N countries are tracked
    across every year (by all-time total) so the legend stays stable;
    everyone else is bucketed into "Other"."""
    top_countries = df.groupby("origin")["quantity_kg"].sum().sort_values(ascending=False).head(top_n).index.tolist()
    view = df.copy()
    view["origin_group"] = view["origin"].where(view["origin"].isin(top_countries), "Other")

    by_year = view.groupby(["year", "origin_group"], as_index=False)["quantity_kg"].sum()
    year_totals = by_year.groupby("year")["quantity_kg"].transform("sum")
    by_year["share_pct"] = by_year["quantity_kg"] / year_totals * 100

    # keep "Other" at the bottom/end of the stack and top countries ordered by overall size
    order = top_countries + (["Other"] if "Other" in by_year["origin_group"].unique() else [])
    fig = px.bar(
        by_year, x="year", y="share_pct", color="origin_group", category_orders={"origin_group": order},
        labels={"year": "Year", "share_pct": "Share of import quantity (%)", "origin_group": "Origin"},
    )
    fig.update_layout(barmode="stack")
    st.plotly_chart(fig, width='stretch')

    latest_year = int(df["year"].max())
    latest = by_year[by_year["year"] == latest_year].sort_values("share_pct", ascending=False)
    top_row = latest.iloc[0]
    st.caption(f"In {latest_year}, {top_row['origin_group']} was the largest source at {top_row['share_pct']:.1f}% of import quantity.")

    with st.expander("View exact figures by year"):
        table = by_year.pivot(index="origin_group", columns="year", values="share_pct").reindex(order)
        st.dataframe(table.round(1).rename_axis("Origin").rename(columns=str), width='stretch')


def render_movers_table(df, current_year, prior_year, top_n=10):
    """Chemicals with the biggest year-over-year change in import quantity,
    ranked by absolute change in kg (not percentage, since a tiny prior-year
    base can make a small change look like a huge percentage swing)."""
    cur = df[df["year"] == current_year].groupby("common_name")["quantity_kg"].sum()
    prev = df[df["year"] == prior_year].groupby("common_name")["quantity_kg"].sum()
    combined = pd.DataFrame({"current": cur, "prior": prev}).fillna(0)
    combined = combined[(combined["current"] > 0) | (combined["prior"] > 0)]
    combined["change_kg"] = combined["current"] - combined["prior"]

    def pct_label(row):
        if row["prior"] == 0:
            return "New"
        if row["current"] == 0:
            return "Discontinued"
        return f"{(row['current'] / row['prior'] - 1) * 100:+.0f}%"

    combined["change_pct"] = combined.apply(pct_label, axis=1)
    combined = combined.reset_index().rename(columns={
        "common_name": "Chemical",
        "prior": f"{prior_year} (kg)",
        "current": f"{current_year} (kg)",
        "change_kg": "Change (kg)",
        "change_pct": "Change (%)",
    })

    gainers = combined.sort_values("Change (kg)", ascending=False).head(top_n)
    decliners = combined.sort_values("Change (kg)", ascending=True).head(top_n)

    col_order = ["Chemical", f"{prior_year} (kg)", f"{current_year} (kg)", "Change (kg)", "Change (%)"]
    fmt = {f"{prior_year} (kg)": "{:,.0f}", f"{current_year} (kg)": "{:,.0f}", "Change (kg)": "{:+,.0f}"}

    st.markdown(f"**Biggest gainers, {prior_year} → {current_year}**")
    st.dataframe(gainers[col_order].style.format(fmt), width='stretch', hide_index=True)

    st.markdown(f"**Biggest decliners, {prior_year} → {current_year}**")
    st.dataframe(decliners[col_order].style.format(fmt), width='stretch', hide_index=True)
