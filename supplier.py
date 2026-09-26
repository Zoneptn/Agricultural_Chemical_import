"""Supplier/company profile logic: pick a manufacturer, importer, or
distributor and see their registration portfolio from reg_no.

master_import has no company-level field (only origin country), so this page
is built entirely from reg_no and can't show import quantity/value for a
specific company — that link doesn't exist anywhere in the data.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from common import not_expired

ROLE_COLUMNS = {
    "Manufacturer (source)": "source",
    "Importer": "importer",
    "Distributor": "distributor",
}

DISPLAY_COLS = {
    "common_name": "Chemical",
    "category": "Category",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "trade_name": "Trade name",
    "reg_no": "Reg. No.",
    "issued": "Issued",
    "expire": "Expires",
}


@st.cache_data
def manufacturer_options(reg_df):
    """source lists one or more manufacturers per row, semicolon-separated —
    split them out into individual, deduplicated entries for the dropdown.
    Near-duplicate spellings (typos in the source data) will appear as
    separate entries; there's no clean way to merge those without guessing."""
    parts = set()
    for cell in reg_df["source"].dropna():
        for part in str(cell).split(";"):
            part = part.strip()
            if part:
                parts.add(part)
    return sorted(parts)


def company_portfolio(reg_df, role, company, active_only):
    """Registrations attributable to `company` in the given `role`.
    Manufacturer uses substring match (a row can list several manufacturers
    together); importer/distributor use exact match (always single-company)."""
    col = ROLE_COLUMNS[role]
    view = not_expired(reg_df) if active_only else reg_df
    if role == "Manufacturer (source)":
        mask = view[col].str.contains(company, na=False, regex=False)
    else:
        mask = view[col] == company
    return view[mask]


def render_supplier_profile(portfolio, role, company):
    if portfolio.empty:
        st.warning(f"No registrations found for this {role.lower()}.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registrations", f"{len(portfolio):,}")
    c2.metric("Distinct chemicals", f"{portfolio['common_name'].nunique():,}")
    c3.metric("Distinct trade names", f"{portfolio['trade_name'].nunique():,}")
    c4.metric("Categories covered", f"{portfolio['category'].nunique():,}")

    st.markdown("**Registrations by category**")
    by_cat = portfolio["category"].value_counts().reset_index()
    by_cat.columns = ["category", "count"]
    fig_cat = px.bar(
        by_cat.sort_values("count", ascending=True), x="count", y="category", orientation="h",
        labels={"count": "Registrations", "category": "Category"},
    )
    st.plotly_chart(fig_cat, width='stretch')

    st.markdown("**Registrations by year issued**")
    by_year = portfolio.dropna(subset=["issued"]).copy()
    by_year["issued_year"] = by_year["issued"].dt.year
    year_counts = by_year.groupby("issued_year").size().reset_index(name="count")
    fig_year = px.bar(
        year_counts, x="issued_year", y="count",
        labels={"issued_year": "Year issued", "count": "Registrations"},
    )
    st.plotly_chart(fig_year, width='stretch')

    st.markdown("**Full portfolio**")
    view = portfolio[list(DISPLAY_COLS.keys())].rename(columns=DISPLAY_COLS).sort_values("Chemical")
    st.dataframe(view, width='stretch', hide_index=True)
    st.download_button(
        "Download portfolio as CSV",
        view.to_csv(index=False).encode("utf-8"),
        f"{company.replace(' ', '_')}_portfolio.csv",
        "text/csv",
    )
