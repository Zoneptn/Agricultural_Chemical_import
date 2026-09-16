import pandas as pd
import plotly.express as px
import streamlit as st

from common import load_master_import, load_classifications, classify_chemical, reload_all

st.set_page_config(page_title="Chemical Comparison", layout="wide")

df = load_master_import()
classification_tables = load_classifications()

st.title("🔬 Chemical Comparison")
st.caption(
    "Compare chemicals side by side over the full year range — including the same "
    "chemical from different origin countries."
)

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

metric_labels = {
    "quantity_kg": "Import quantity (kg)",
    "value_bht": "Import value (THB)",
    "ai_kg": "Active ingredient (kg)",
    "price_thb": "Average price (THB/kg)",
}
metric_choice = st.radio(
    "Metric", list(metric_labels.keys()), format_func=lambda k: metric_labels[k], horizontal=True
)

num_chem = st.slider("Number of chemicals to compare", min_value=2, max_value=10, value=3, key="cmp_num")

PLACEHOLDER = "— Select —"
ALL_COUNTRIES = "All countries"
chem_options = [PLACEHOLDER] + sorted(df["common_name"].unique())
country_options = [ALL_COUNTRIES] + sorted(df["origin"].unique())

st.markdown("**Pick a chemical (and, optionally, a specific origin country) for each slot:**")

specs = []  # list of (chemical, country_or_None)
slot_idx = 0
while slot_idx < num_chem:
    st.markdown(f"Slot {slot_idx + 1}")
    c1, c2 = st.columns(2)
    with c1:
        chem_val = st.selectbox("Chemical", chem_options, key=f"cmp_chem_{slot_idx}", label_visibility="collapsed")
    with c2:
        country_val = st.selectbox("Country", country_options, key=f"cmp_country_{slot_idx}", label_visibility="collapsed")
    if chem_val != PLACEHOLDER:
        specs.append((chem_val, None if country_val == ALL_COUNTRIES else country_val))
    slot_idx += 1

# de-duplicate identical (chemical, country) picks while preserving order
specs = list(dict.fromkeys(specs))

st.divider()

if not specs:
    st.info("Pick at least one chemical above (in any slot) to see the comparison.")
    st.stop()

# build a readable label per spec and a combined dataframe across all specs
frames = []
labels = []
for chem, country in specs:
    label = chem if country is None else f"{chem} ({country})"
    labels.append(label)
    sub = df[df["common_name"] == chem]
    if country is not None:
        sub = sub[sub["origin"] == country]
    sub = sub.copy()
    sub["_label"] = label
    frames.append(sub)

combined = pd.concat(frames, ignore_index=True)

if combined.empty:
    st.warning("None of the selected chemical/country combinations have any import data.")
    st.stop()

# ---------------- Line chart: movement across all years, one line per slot ----------------
st.subheader(f"{metric_labels[metric_choice]} by year")

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

# ---------------- Summary totals ----------------
st.markdown("**Summary totals**")
summary = combined.groupby("_label", as_index=False).agg(
    total_quantity_kg=("quantity_kg", "sum"),
    total_value_bht=("value_bht", "sum"),
    total_ai_kg=("ai_kg", "sum"),
    origin_countries=("origin", "nunique"),
    first_year=("year", "min"),
    last_year=("year", "max"),
)
summary["avg_price_thb_per_kg"] = summary["total_value_bht"] / summary["total_quantity_kg"].replace(0, pd.NA)
summary = summary.rename(columns={
    "_label": "Chemical (country)",
    "total_quantity_kg": "Total quantity (kg)",
    "total_value_bht": "Total value (THB)",
    "avg_price_thb_per_kg": "Avg price (THB/kg)",
    "total_ai_kg": "Total AI (kg)",
    "origin_countries": "# origin countries",
    "first_year": "First year",
    "last_year": "Last year",
})[[
    "Chemical (country)", "Total quantity (kg)", "Total value (THB)", "Avg price (THB/kg)",
    "Total AI (kg)", "# origin countries", "First year", "Last year",
]].sort_values("Total quantity (kg)", ascending=False)

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

# ---------------- IRAC / HRAC / FRAC classification detail (per unique chemical, ignoring country) ----------------
st.markdown("**Classification detail (IRAC / HRAC / FRAC)**")
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
