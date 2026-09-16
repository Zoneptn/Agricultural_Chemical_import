"""Trend, origin-breakdown, and data-table rendering for the Overview page."""
import pandas as pd
import plotly.express as px
import streamlit as st

METRIC_LABELS = {
    "quantity_kg": "Import quantity (kg)",
    "value_bht": "Import value (THB)",
    "ai_kg": "Active ingredient (kg)",
    "price_thb": "Average price (THB/kg)",
}


def render_trend_chart(filtered, sel_names, metric_choice):
    group_cols = ["year", "common_name"] if sel_names else ["year"]

    if metric_choice == "price_thb":
        trend = filtered.groupby(group_cols, as_index=False)[["value_bht", "quantity_kg"]].sum()
        trend["price_thb"] = trend["value_bht"] / trend["quantity_kg"].replace(0, pd.NA)
        y_col = "price_thb"
    else:
        trend = filtered.groupby(group_cols, as_index=False)[metric_choice].sum()
        y_col = metric_choice

    if sel_names:
        # one or more chemicals picked -> a line per chemical
        fig = px.line(
            trend, x="year", y=y_col, color="common_name", markers=True,
            labels={"year": "Year", y_col: METRIC_LABELS[metric_choice], "common_name": "Chemical"},
        )
    else:
        # no chemical picked -> single aggregate line (500+ chemicals would be unreadable split out)
        fig = px.line(
            trend, x="year", y=y_col, markers=True, labels={"year": "Year", y_col: METRIC_LABELS[metric_choice]}
        )
        st.caption("Pick one or more chemicals above to split this line by chemical.")
    st.plotly_chart(fig, width='stretch')


def render_origin_chart(filtered, metric_choice):
    if metric_choice == "price_thb":
        by_origin = filtered.groupby("origin", as_index=False)[["value_bht", "quantity_kg"]].sum()
        by_origin["price_thb"] = by_origin["value_bht"] / by_origin["quantity_kg"].replace(0, pd.NA)
    else:
        by_origin = filtered.groupby("origin", as_index=False)[metric_choice].sum()
    by_origin = by_origin.sort_values(metric_choice, ascending=False).head(15)

    fig = px.bar(
        by_origin, x=metric_choice, y="origin", orientation="h",
        labels={metric_choice: METRIC_LABELS[metric_choice], "origin": "Origin"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width='stretch')


def render_data_table(filtered):
    st.dataframe(filtered.sort_values("year", ascending=False), width='stretch')
    st.download_button(
        "Download filtered data as CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "filtered_chemical_import.csv",
        "text/csv",
    )
