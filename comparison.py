"""Slot picking, charting, and summary logic for the Chemical Comparison page.

Each slot picks its own chemical, concentration, formulation type, and origin
country, with concentration/formulation/country narrowed to that slot's own
chemical (and narrower picks within the slot) — so two slots can hold the same
chemical but different variants or origin countries, and be compared directly.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from common import classify_by_component

PLACEHOLDER = "— Select —"
ALL_CONCENTRATIONS = "All concentrations"
ALL_FORMULATIONS = "All formulation types"
ALL_COUNTRIES = "All countries"

SUMMARY_COLS = {
    "_label": "Chemical",
    "total_quantity_kg": "Total quantity (kg)",
    "total_value_bht": "Total value (THB)",
    "avg_price_thb_per_kg": "Avg price (THB/kg)",
    "total_ai_kg": "Total AI (kg)",
    "origin_countries": "# origin countries",
    "first_year": "First year",
    "last_year": "Last year",
}


def _slot_label(spec):
    """A readable legend/table label: the chemical name, plus whichever of
    concentration/formulation/country were actually narrowed for this slot."""
    extras = [v for v in (spec["concentration"], spec["formulation_type"], spec["country"]) if v]
    return spec["chemical"] if not extras else f"{spec['chemical']} ({', '.join(extras)})"


def render_slot_pickers(df, num_chem):
    """Renders `num_chem` rows, each with 4 dropdowns: chemical, concentration,
    formulation type, and origin country. The latter three are narrowed to that
    row's own chemical (and to each other within the row) and default to an
    "All ..." aggregate option. Returns a de-duplicated list of spec dicts:
    {"chemical", "concentration", "formulation_type", "country"} — the latter
    three are None when left on their "All ..." option."""
    chem_options = [PLACEHOLDER] + sorted(df["common_name"].unique())

    st.caption("Each row is one chemical to compare. Leave a field on \"All ...\" to aggregate across it.")

    specs = []
    for slot_idx in range(num_chem):
        st.markdown(f"**Chemical {slot_idx + 1}**")
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            chem_val = st.selectbox(
                "Chemical", chem_options, key=f"cmp_chem_{slot_idx}", label_visibility="collapsed"
            )

        chem_scope = df[df["common_name"] == chem_val] if chem_val != PLACEHOLDER else df.iloc[0:0]

        with c2:
            conc_opts = [ALL_CONCENTRATIONS] + sorted(chem_scope["concentration"].unique())
            conc_val = st.selectbox(
                "Concentration", conc_opts, key=f"cmp_conc_{slot_idx}", label_visibility="collapsed"
            )
        conc_scope = chem_scope if conc_val == ALL_CONCENTRATIONS else chem_scope[chem_scope["concentration"] == conc_val]

        with c3:
            form_opts = [ALL_FORMULATIONS] + sorted(conc_scope["formulation_type"].unique())
            form_val = st.selectbox(
                "Formulation type", form_opts, key=f"cmp_form_{slot_idx}", label_visibility="collapsed"
            )
        form_scope = conc_scope if form_val == ALL_FORMULATIONS else conc_scope[conc_scope["formulation_type"] == form_val]

        with c4:
            country_opts = [ALL_COUNTRIES] + sorted(form_scope["origin"].unique())
            country_val = st.selectbox(
                "Country", country_opts, key=f"cmp_country_{slot_idx}", label_visibility="collapsed"
            )

        if chem_val != PLACEHOLDER:
            specs.append({
                "chemical": chem_val,
                "concentration": None if conc_val == ALL_CONCENTRATIONS else conc_val,
                "formulation_type": None if form_val == ALL_FORMULATIONS else form_val,
                "country": None if country_val == ALL_COUNTRIES else country_val,
            })

    # de-duplicate identical specs while preserving pick order
    seen = set()
    deduped = []
    for spec in specs:
        key = (spec["chemical"], spec["concentration"], spec["formulation_type"], spec["country"])
        if key not in seen:
            seen.add(key)
            deduped.append(spec)
    return deduped


def build_combined_frame(df, specs):
    """Builds one dataframe across all specs, tagged with a readable `_label`
    column per spec for charting/grouping."""
    frames = []
    for spec in specs:
        sub = df[df["common_name"] == spec["chemical"]]
        if spec["concentration"]:
            sub = sub[sub["concentration"] == spec["concentration"]]
        if spec["formulation_type"]:
            sub = sub[sub["formulation_type"] == spec["formulation_type"]]
        if spec["country"]:
            sub = sub[sub["origin"] == spec["country"]]
        sub = sub.copy()
        sub["_label"] = _slot_label(spec)
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
        labels={"year": "Year", y_col: metric_labels[metric_choice], "_label": "Chemical"},
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
    """One expander per unique chemical, so a mixture's several components
    (and each component's potentially long, bilingual mode-of-action text)
    get room to read instead of being crammed into wide table cells."""
    unique_chems = list(dict.fromkeys(spec["chemical"] for spec in specs))
    for name in unique_chems:
        breakdown = classify_by_component(name, classification_tables)
        with st.expander(name, expanded=(len(unique_chems) == 1)):
            for entry in breakdown:
                is_mixture = len(breakdown) > 1
                if is_mixture:
                    st.markdown(f"**Component: {entry['component']}**")
                if not entry["matches"]:
                    st.caption("No IRAC/HRAC/FRAC match found for this component.")
                else:
                    for m in entry["matches"]:
                        st.markdown(f"**{m['system']}** — Code {m['code']}")
                        st.markdown(f"- Physiological category: {m['physiological_category']}")
                        st.markdown(f"- Mode of action: {m['mode_of_action']}")
                        st.markdown(f"- Chemical class/group: {m['chemical_class_group']}")
                if is_mixture and entry is not breakdown[-1]:
                    st.divider()
