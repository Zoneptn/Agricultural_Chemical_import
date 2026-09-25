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
