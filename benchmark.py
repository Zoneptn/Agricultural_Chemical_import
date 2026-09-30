"""SHK Benchmark: how one distributor's registration portfolio compares to
the total market, built from reg_no (registration counts, categories,
distributors) plus master_import (total import volume per chemical, used
only for the market-opportunity gap analysis below).

master_import has no company-level field, so nothing here claims to show
SHK's own import volume or value — only registration-count-based market
position, which is the only company-level signal the data actually has.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from common import not_expired

DEFAULT_DISTRIBUTOR = "สหายเกษตร บจก."


def distributor_options(reg_df):
    return sorted(reg_df["distributor"].unique())


def overview_metrics(reg_df, distributor, active_only):
    """Headline counts: how big is this distributor's portfolio, and where
    does it rank against every other distributor by active registration
    count."""
    view = not_expired(reg_df) if active_only else reg_df
    company = view[view["distributor"] == distributor]

    counts = view.groupby("distributor").size().sort_values(ascending=False)
    total_distributors = len(counts)
    rank = int(counts.index.get_loc(distributor) + 1) if distributor in counts.index else None

    market_total = len(view)
    company_total = len(company)
    share_pct = (company_total / market_total * 100) if market_total else 0.0

    return {
        "company_registrations": company_total,
        "distinct_chemicals": company["common_name"].nunique(),
        "categories_covered": company["category"].nunique(),
        "market_share_pct": share_pct,
        "rank": rank,
        "total_distributors": total_distributors,
    }


def category_benchmark(reg_df, distributor, active_only):
    """Per category: this distributor's registration count, the market
    total, its share of that category, and how many distinct distributors
    (including itself) compete in it. Sorted by market size so the
    categories that matter most come first."""
    view = not_expired(reg_df) if active_only else reg_df
    company = view[view["distributor"] == distributor]

    company_counts = company.groupby("category").size()
    market_counts = view.groupby("category").size()
    distinct_distributors = view.groupby("category")["distributor"].nunique()

    out = pd.DataFrame({
        "company_registrations": company_counts,
        "market_registrations": market_counts,
        "distinct_distributors": distinct_distributors,
    }).fillna(0).astype({"company_registrations": int, "market_registrations": int, "distinct_distributors": int})
    out["share_pct"] = (out["company_registrations"] / out["market_registrations"] * 100).round(1)
    return out.reset_index().rename(columns={"category": "Category"}).sort_values(
        "market_registrations", ascending=False
    )


def competing_distributors(reg_df, distributor, category, active_only, top_n=15):
    """Ranks every distributor active in `category` by registration count,
    so the user can see exactly who they're up against in a category they
    care about, and where they themselves land in that ranking."""
    view = not_expired(reg_df) if active_only else reg_df
    scope = view[view["category"] == category]
    counts = scope.groupby("distributor").size().reset_index(name="Registrations")
    counts = counts.sort_values("Registrations", ascending=False).head(top_n)
    counts["Is this company"] = counts["distributor"] == distributor
    return counts.rename(columns={"distributor": "Distributor"})


def registration_trend(reg_df, distributor):
    """This distributor's share of registrations issued, by year, against
    the market total issued that year — a raw side-by-side count would be
    dwarfed by the market total, so share is the readable version."""
    view = reg_df.dropna(subset=["issued"]).copy()
    view["issued_year"] = view["issued"].dt.year

    market_by_year = view.groupby("issued_year").size().rename("market_total")
    company_by_year = view[view["distributor"] == distributor].groupby("issued_year").size().rename("company_total")

    out = pd.concat([market_by_year, company_by_year], axis=1).fillna(0)
    out["company_total"] = out["company_total"].astype(int)
    out["market_total"] = out["market_total"].astype(int)
    out["share_pct"] = (out["company_total"] / out["market_total"].replace(0, pd.NA) * 100).round(1)
    return out.reset_index().rename(columns={"issued_year": "year"})


def chemicals_registered_with_rank(reg_df, master_df, distributor, active_only):
    """Chemicals this distributor is registered for, matched to their total
    market import volume and overall volume rank across every chemical in
    master_import — shows whether the company's portfolio leans toward the
    market's top sellers or its long tail."""
    view = not_expired(reg_df) if active_only else reg_df
    company_names = set(view[view["distributor"] == distributor]["common_name"].str.lower())

    totals = master_df.groupby("common_name", as_index=False)["quantity_kg"].sum()
    totals["_norm"] = totals["common_name"].str.lower()
    totals["rank"] = totals["quantity_kg"].rank(ascending=False, method="min").astype(int)

    matched = totals[totals["_norm"].isin(company_names)].sort_values("quantity_kg", ascending=False)
    return matched[["common_name", "quantity_kg", "rank"]].rename(
        columns={"common_name": "Chemical", "quantity_kg": "Total market quantity (kg)", "rank": "Market rank"}
    )


def chemical_gap_analysis(reg_df, master_df, distributor, active_only, top_n=20):
    """The market's biggest chemicals by total import volume that this
    distributor holds NO active registration for — a market-opportunity
    list, ranked purely by size of the volume being missed."""
    view = not_expired(reg_df) if active_only else reg_df
    company_names = set(view[view["distributor"] == distributor]["common_name"].str.lower())

    totals = master_df.groupby("common_name", as_index=False)["quantity_kg"].sum()
    totals["_norm"] = totals["common_name"].str.lower()

    gap = totals[~totals["_norm"].isin(company_names)].sort_values("quantity_kg", ascending=False).head(top_n)
    return gap[["common_name", "quantity_kg"]].rename(
        columns={"common_name": "Chemical", "quantity_kg": "Total market quantity (kg)"}
    )


def render_benchmark(reg_df, master_df, distributor, active_only):
    metrics = overview_metrics(reg_df, distributor, active_only)
    if metrics["company_registrations"] == 0:
        st.warning(f"No {'active ' if active_only else ''}registrations found for this distributor.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registrations", f"{metrics['company_registrations']:,}")
    c2.metric("Distinct chemicals", f"{metrics['distinct_chemicals']:,}")
    c3.metric("Categories covered", f"{metrics['categories_covered']:,}")
    rank_label = f"#{metrics['rank']} of {metrics['total_distributors']}" if metrics["rank"] else "n/a"
    c4.metric("Rank among distributors", rank_label)
    st.caption(f"Holds {metrics['market_share_pct']:.1f}% of all {'active ' if active_only else ''}registrations market-wide, by registration count.")

    st.markdown("**Category benchmark: this company vs. the total market**")
    cat_bench = category_benchmark(reg_df, distributor, active_only)
    cat_bench_shown = cat_bench[cat_bench["company_registrations"] > 0]
    if cat_bench_shown.empty:
        st.info("This distributor has no registrations in any category to benchmark.")
    else:
        fig = px.bar(
            cat_bench_shown.sort_values("share_pct", ascending=True),
            x="share_pct", y="Category", orientation="h",
            labels={"share_pct": "Share of category's registrations (%)", "Category": "Category"},
            text="share_pct",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        st.plotly_chart(fig, width='stretch')

        table = cat_bench_shown.rename(columns={
            "company_registrations": "This company",
            "market_registrations": "Market total",
            "distinct_distributors": "Distinct distributors",
            "share_pct": "Share (%)",
        })
        st.dataframe(
            table[["Category", "This company", "Market total", "Distinct distributors", "Share (%)"]],
            width='stretch', hide_index=True,
        )

    st.markdown("**Who else competes in a category?**")
    categories_present = sorted(cat_bench_shown["Category"].unique()) if not cat_bench_shown.empty else []
    if categories_present:
        chosen_category = st.selectbox("Category", categories_present, key="bench_category")
        competitors = competing_distributors(reg_df, distributor, chosen_category, active_only)
        st.dataframe(
            competitors[["Distributor", "Registrations", "Is this company"]],
            width='stretch', hide_index=True,
        )
    else:
        st.info("No category with an active registration to look up competitors for.")

    st.markdown("**Registration share by year issued**")
    trend = registration_trend(reg_df, distributor)
    trend_present = trend[trend["company_total"] > 0]
    if trend_present.empty:
        st.info("No dated registrations on record for this distributor.")
    else:
        fig_trend = px.line(
            trend_present, x="year", y="share_pct", markers=True,
            labels={"year": "Year issued", "share_pct": "Share of that year's registrations (%)"},
        )
        st.plotly_chart(fig_trend, width='stretch')

    st.markdown("**This company's chemicals, ranked by market size**")
    st.caption("Where each of this company's registered chemicals ranks by total import volume across the whole market — a high rank number means it's a niche product market-wide, not necessarily for this company.")
    ranked = chemicals_registered_with_rank(reg_df, master_df, distributor, active_only)
    if ranked.empty:
        st.info("None of this company's registered chemicals appear in master_import's chemical names.")
    else:
        st.dataframe(
            ranked.style.format({"Total market quantity (kg)": "{:,.0f}"}),
            width='stretch', hide_index=True,
        )

    st.markdown("**Market opportunity: biggest chemicals this company doesn't carry**")
    st.caption("Ranked by total market import volume, among chemicals this company holds no active registration for.")
    gap = chemical_gap_analysis(reg_df, master_df, distributor, active_only)
    st.dataframe(
        gap.style.format({"Total market quantity (kg)": "{:,.0f}"}),
        width='stretch', hide_index=True,
    )
