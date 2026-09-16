"""Slot picking, charting, and summary logic for the Chemical Comparison page."""
import pandas as pd
import plotly.express as px
import streamlit as st

from common import classify_chemical

PLACEHOLDER = "— Select —"
ALL_COUNTRIES = "All countries"

SUMMARY_COLS = {
    "_label": "Chemical (country)",
    "total_quantity_kg": "Total quantity (kg)",
    "total_value_bht": "Total value (THB)",
    "avg_price_thb_per_kg": "Avg price (THB/kg)",
    "total_ai_kg": "Total AI (kg)",
    "origin_countries": "# origin countries",
    "first_year": "First year",
    "last_year": "Last year",
}


def render_slot_pickers(df, num_chem):
    """Renders `num_chem` (chemical, country) picker rows. Returns a de-duplicated
    list of (chemical, country_or_None) tuples, in pick order. country is None
    when the slot's country box is left on "All countries"."""
    chem_options = [PLACEHOLDER] + sorted(df["common_name"].unique())
    country_options = [ALL_COUNTRIES] + sorted(df["origin"].unique())

    st.markdown("**Pick a chemical (and, optionally, a specific origin country) for each slot:**")

    specs = []
    for slot_idx in range(num_chem):
        st.markdown(f"Slot {slot_idx + 1}")
        c1, c2 = st.columns(2)
        with c1:
            chem_val = st.selectbox(
                "Chemical", chem_options, key=f"cmp_chem_{slot_idx}", label_visibility="collapsed"
            )
        with c2:
            country_val = st.selectbox(
                "Country", country_options, key=f"cmp_country_{slot_idx}", label_visibility="collapsed"
            )
        if chem_val != PLACEHOLDER:
            specs.append((chem_val, None if country_val == ALL_COUNTRIES else country_val))

    # de-duplicate identical (chemical, country) picks while preserving order
    return list(dict.fromkeys(specs))


def build_combined_frame(df, specs):
    """Builds one dataframe across all (chemical, country) specs, tagged with a
    readable `_label` column per spec for charting/grouping."""
    frames = []
    for chem, country in specs:
        label = chem if country is None else f"{chem} ({country})"
        sub = df[df["common_name"] == chem]
        if country is not None:
            sub = sub[sub["origin"] == country]
        sub = sub.copy()
        sub["_label"] = label
        frames.append(sub)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def render_comparison_trend(combined, metric_choice, metric_labels):
    if metric_choice == "price_thb":
        trend = combined.groupby(["year", "_label"], as_index=False)[["value_bht", "quantity_kg"]].sum()
        trend["price_thb"] = trend["value_bht"] / trend["quantity_kg"].replace(0, pd.NA)
        y_col = "price_thb"
    else:
        trend = combined.groupby(["year", "_label"], as_index=False)[metric_choice].sum()
        y_col = metric_choice

    fig = px.line(
        trend, x="year", y=y_col, color="_label", markers=True,
        labels={"year": "Year", y_col: metric_labels[metric_choice], "_label": "Chemical (country)"},
    )
    st.plotly_chart(fig, width='stretch')


def render_comparison_summary(combined):
    summary = combined.groupby("_label", as_index=False).agg(
        total_quantity_kg=("quantity_kg", "sum"),
        total_value_bht=("value_bht", "sum"),
        total_ai_kg=("ai_kg", "sum"),
        origin_countries=("origin", "nunique"),
        first_year=("year", "min"),
        last_year=("year", "max"),
    )
    summary["avg_price_thb_per_kg"] = summary["total_value_bht"] / summary["total_quantity_kg"].replace(0, pd.NA)
    summary = summary.rename(columns=SUMMARY_COLS)[list(SUMMARY_COLS.values())]
    summary = summary.sort_values("Total quantity (kg)", ascending=False)

    st.dataframe(
        summary.style.format({
            "Total quantity (kg)": "{:,.0f}",
            "Total value (THB)": "{:,.0f}",
            "Avg price (THB/kg)": "{:,.2f}",
            "Total AI (kg)": "{:,.0f}",
        }),
        width='stretch',
        hide_index=True,
    )


def render_comparison_classification(specs, classification_tables):
    unique_chems = list(dict.fromkeys(chem for chem, _ in specs))
    detail_rows = []
    for name in unique_chems:
        hits = classify_chemical(name, classification_tables)
        if hits:
            for h in hits:
                detail_rows.append({"Chemical": name, **h})
        else:
            detail_rows.append({
                "Chemical": name, "Component": "", "System": "—",
                "Physiological category": "No IRAC/HRAC/FRAC match found",
                "Mode of action": "", "Chemical class/group": "", "Code": "",
            })
    st.dataframe(pd.DataFrame(detail_rows), width='stretch', hide_index=True)
