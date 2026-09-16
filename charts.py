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


def _quantity_and_price(df, group_cols):
    """Both metrics in one pass: summed quantity, and value/quantity price."""
    agg = df.groupby(group_cols, as_index=False)[["quantity_kg", "value_bht"]].sum()
    agg["price_thb"] = agg["value_bht"] / agg["quantity_kg"].replace(0, pd.NA)
    return agg


def render_trend_chart(filtered, sel_names):
    """Always shows both charts — quantity and average price only matter
    here, so there's nothing to choose between."""
    group_cols = ["year", "common_name"] if sel_names else ["year"]
    trend = _quantity_and_price(filtered, group_cols)
    color = "common_name" if sel_names else None

    st.markdown("**Import quantity (kg) by year**")
    fig_qty = px.line(
        trend, x="year", y="quantity_kg", color=color, markers=True,
        labels={"year": "Year", "quantity_kg": "Import quantity (kg)", "common_name": "Chemical"},
    )
    st.plotly_chart(fig_qty, width='stretch')

    st.markdown("**Average price (THB/kg) by year**")
    fig_price = px.line(
        trend, x="year", y="price_thb", color=color, markers=True,
        labels={"year": "Year", "price_thb": "Average price (THB/kg)", "common_name": "Chemical"},
    )
    st.plotly_chart(fig_price, width='stretch')

    if not sel_names:
        st.caption("Pick one or more chemicals above to split these lines by chemical.")


def render_origin_chart(filtered):
    """Always shows both — quantity and average price by origin country."""
    by_origin = _quantity_and_price(filtered, ["origin"])

    st.markdown("**Import quantity (kg) by origin country**")
    top_qty = by_origin.sort_values("quantity_kg", ascending=False).head(15)
    fig_qty = px.bar(
        top_qty, x="quantity_kg", y="origin", orientation="h",
        labels={"quantity_kg": "Import quantity (kg)", "origin": "Origin"},
    )
    fig_qty.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_qty, width='stretch')

    st.markdown("**Average price (THB/kg) by origin country**")
    top_price = by_origin.sort_values("price_thb", ascending=False).head(15)
    fig_price = px.bar(
        top_price, x="price_thb", y="origin", orientation="h",
        labels={"price_thb": "Average price (THB/kg)", "origin": "Origin"},
    )
    fig_price.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_price, width='stretch')


def render_data_table(filtered):
    st.dataframe(filtered.sort_values("year", ascending=False), width='stretch')
    st.download_button(
        "Download filtered data as CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "filtered_chemical_import.csv",
        "text/csv",
    )
