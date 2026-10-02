"""Market-summary logic: category trend, origin-country market share, and
year-over-year mover analysis, all built from master_import.

master_import carries its own category column directly (every row filled in,
no gaps), so it's used as-is here. An earlier version of this file derived
category by mapping each common_name to its most-common category in reg_no
instead — that was dropped once master_import's own column turned out to
disagree with the reg_no-derived guess on about 31% of import volume, which
makes the native column the more trustworthy one for a given shipment.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from common import aggregate_with_price


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
        priced = matched[matched["value_bht"] > 0]
        priced_qty = priced["quantity_kg"].sum()
        avg_price = (priced["value_bht"].sum() / priced_qty) if priced_qty else pd.NA
        summary_rows.append({
            "Keyword": kw,
            "Matched products": len(names),
            "Total quantity (kg)": total_qty,
            "Total value (THB)": total_val,
            "Avg price (THB/kg)": avg_price,
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
    by_year = aggregate_with_price(combined, ["year", "keyword"])

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

    other_share = df[df["category"] == "other"]["quantity_kg"].sum() / df["quantity_kg"].sum()
    st.caption(f"\"other\" is master_import's own catch-all category, not a data gap — it's {other_share:.0%} of import volume.")


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


HHI_UNCONCENTRATED = 1500
HHI_HIGHLY_CONCENTRATED = 2500


def concentration_label(hhi):
    if hhi < HHI_UNCONCENTRATED:
        return "Unconcentrated"
    if hhi < HHI_HIGHLY_CONCENTRATED:
        return "Moderately concentrated"
    return "Highly concentrated"


def compute_origin_hhi(df):
    """Herfindahl-Hirschman Index of origin-country concentration, by
    category and year: sum of each origin country's squared percentage
    share of that category/year's import quantity. Ranges from near 0 (many
    countries splitting the volume evenly) to 10,000 (one country holds all
    of it) — a single number for "how many eggs are in how few baskets" on
    the supply side, standing in for the stacked-share chart above.

    Uses the standard DOJ/FTC merger-guideline bands (<1,500 unconcentrated,
    1,500-2,500 moderately concentrated, >2,500 highly concentrated) as a
    rule-of-thumb reference — those were written for firms' revenue shares,
    but the same math reads the same way applied to supplying countries'
    volume shares."""
    totals = df.groupby(["category", "year", "origin"], as_index=False)["quantity_kg"].sum()
    group_totals = totals.groupby(["category", "year"])["quantity_kg"].transform("sum")
    totals["share_pct"] = totals["quantity_kg"] / group_totals * 100

    hhi = totals.groupby(["category", "year"], as_index=False).apply(
        lambda g: pd.Series({"hhi": (g["share_pct"] ** 2).sum()}), include_groups=False
    )

    top = (
        totals.sort_values("share_pct", ascending=False)
        .groupby(["category", "year"], as_index=False)
        .head(1)[["category", "year", "origin", "share_pct"]]
        .rename(columns={"origin": "top_origin", "share_pct": "top_origin_share_pct"})
    )
    return hhi.merge(top, on=["category", "year"])


def render_concentration_index(df):
    """Current-year snapshot table plus a year-by-year trend of origin-country
    concentration (HHI) per category, so a rising line flags a category
    that's becoming more dependent on fewer supplying countries over time."""
    hhi_df = compute_origin_hhi(df)
    hhi_df["Concentration"] = hhi_df["hhi"].apply(concentration_label)

    latest_year = int(df["year"].max())
    latest = hhi_df[hhi_df["year"] == latest_year].sort_values("hhi", ascending=False)

    st.caption(
        f"Herfindahl-Hirschman Index (HHI) of import quantity by origin country within each category — "
        f"how dominated a category is by a handful of supplying countries, vs. spread across many. "
        f"<{HHI_UNCONCENTRATED:,} unconcentrated · {HHI_UNCONCENTRATED:,}–{HHI_HIGHLY_CONCENTRATED:,} "
        f"moderately concentrated · >{HHI_HIGHLY_CONCENTRATED:,} highly concentrated."
    )

    table = latest.rename(columns={
        "category": "Category", "hhi": "HHI", "top_origin": "Top origin",
        "top_origin_share_pct": "Top origin share (%)",
    })
    st.dataframe(
        table[["Category", "HHI", "Concentration", "Top origin", "Top origin share (%)"]].style.format(
            {"HHI": "{:,.0f}", "Top origin share (%)": "{:.1f}"}
        ),
        width='stretch', hide_index=True,
    )

    st.markdown(f"**HHI trend by year**")
    fig = px.line(
        hhi_df.sort_values("year"), x="year", y="hhi", color="category", markers=True,
        labels={"year": "Year", "hhi": "HHI", "category": "Category"},
    )
    fig.add_hline(y=HHI_UNCONCENTRATED, line_dash="dot", line_color="gray")
    fig.add_hline(y=HHI_HIGHLY_CONCENTRATED, line_dash="dot", line_color="gray")
    st.plotly_chart(fig, width='stretch')


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
