"""Cumulative-view logic: running totals over time, and Pareto (80/20)
breakdowns of which chemicals/categories/countries drive total import volume.
Built entirely from master_import.
"""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def render_cumulative_trend(df, sel_names):
    """Running (cumulative) total import quantity by year — an ever-growing
    line rather than a per-year bar, so you can read off "how much of X has
    been imported in total by year Y". One line per chemical if any are
    picked, otherwise a single line for the whole market."""
    if sel_names:
        view = df[df["common_name"].isin(sel_names)]
        group_cols = ["year", "common_name"]
    else:
        view = df
        group_cols = ["year"]

    by_year = view.groupby(group_cols, as_index=False)["quantity_kg"].sum()

    if sel_names:
        by_year = by_year.sort_values(["common_name", "year"])
        by_year["cumulative_kg"] = by_year.groupby("common_name")["quantity_kg"].cumsum()
        color = "common_name"
    else:
        by_year = by_year.sort_values("year")
        by_year["cumulative_kg"] = by_year["quantity_kg"].cumsum()
        color = None

    fig = px.line(
        by_year, x="year", y="cumulative_kg", color=color, markers=True,
        labels={"year": "Year", "cumulative_kg": "Cumulative import quantity (kg)", "common_name": "Chemical"},
    )
    st.plotly_chart(fig, width='stretch')
    if not sel_names:
        st.caption("Pick one or more chemicals above to split this into per-chemical cumulative lines.")


def render_pareto(df, dimension_col, dimension_label, dimension_plural, top_n=15):
    """Pareto view: entities (chemicals/categories/countries) ranked by total
    import quantity, as bars, with a cumulative-share line on a second axis —
    plus a callout for how many entities it actually takes to reach 80% of
    total volume, since that count is usually the useful headline number."""
    totals = df.groupby(dimension_col)["quantity_kg"].sum().sort_values(ascending=False)
    total_all = totals.sum()
    cum_pct = totals.cumsum() / total_all * 100

    n_for_80 = int((cum_pct <= 80).sum()) + 1
    n_for_80 = min(n_for_80, len(totals))
    st.metric(f"{dimension_plural} needed to reach 80% of total volume", f"{n_for_80} of {len(totals)}")

    display_n = min(top_n, len(totals))
    display_totals = totals.head(display_n)
    display_cum = cum_pct.head(display_n)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=display_totals.index, y=display_totals.values, name="Quantity (kg)"), secondary_y=False
    )
    fig.add_trace(
        go.Scatter(x=display_cum.index, y=display_cum.values, name="Cumulative %", mode="lines+markers"),
        secondary_y=True,
    )
    fig.update_yaxes(title_text="Quantity (kg)", secondary_y=False)
    fig.update_yaxes(title_text="Cumulative % of total volume", range=[0, 105], secondary_y=True)
    fig.update_layout(xaxis_title=dimension_label, xaxis_tickangle=-45, legend=dict(orientation="h"))
    st.plotly_chart(fig, width='stretch')
    st.caption(f"Showing the top {display_n} of {len(totals)} {dimension_label.lower()}s by import quantity.")
