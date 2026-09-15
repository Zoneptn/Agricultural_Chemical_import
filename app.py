import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Chemical Import Dashboard", layout="wide")

DATA_PATH = "chemical_import_database.xlsx"


@st.cache_data
def load_data():
    df = pd.read_excel(DATA_PATH, sheet_name="master_import")
    # normalize text columns for reliable filtering (fillna BEFORE astype(str),
    # since pyarrow-backed string columns keep NaN as float, not the string "nan")
    df["formulation_type"] = df["formulation_type"].fillna("Unspecified")
    for col in ["common_name", "concentration", "formulation_type", "origin"]:
        df[col] = df[col].astype(str).str.strip()
    return df


df = load_data()

st.title("🧪 Chemical Import Dashboard")
st.caption("Import volume by chemical, concentration, formulation, and origin country")

# ---------------- Sidebar: reload only ----------------
st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    load_data.clear()
    st.rerun()

# ---------------- Filters (main area, cascading) ----------------
st.subheader("Filters")

filtered = df.copy()

row1_col1, row1_col2 = st.columns(2)
with row1_col1:
    common_names = sorted(filtered["common_name"].unique())
    sel_names = st.multiselect("Chemical (common name)", common_names)
    if sel_names:
        filtered = filtered[filtered["common_name"].isin(sel_names)]

with row1_col2:
    concentrations = sorted(filtered["concentration"].unique())
    sel_conc = st.multiselect("Concentration", concentrations)
    if sel_conc:
        filtered = filtered[filtered["concentration"].isin(sel_conc)]

row2_col1, row2_col2 = st.columns(2)
with row2_col1:
    formulations = sorted(filtered["formulation_type"].unique())
    sel_form = st.multiselect("Formulation type", formulations)
    if sel_form:
        filtered = filtered[filtered["formulation_type"].isin(sel_form)]

with row2_col2:
    origins = sorted(filtered["origin"].unique())
    sel_origin = st.multiselect("Origin country", origins)
    if sel_origin:
        filtered = filtered[filtered["origin"].isin(sel_origin)]

year_min, year_max = int(df["year"].min()), int(df["year"].max())
sel_years = st.slider("Year range", year_min, year_max, (year_min, year_max))
filtered = filtered[(filtered["year"] >= sel_years[0]) & (filtered["year"] <= sel_years[1])]

st.divider()

# ---------------- Summary metrics ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Matching rows", f"{len(filtered):,}")
c2.metric("Total quantity (kg)", f"{filtered['quantity_kg'].sum():,.0f}")
c3.metric("Total value (THB)", f"{filtered['value_bht'].sum():,.0f}")
c4.metric("Total active ingredient (kg)", f"{filtered['ai_kg'].sum():,.0f}")

st.divider()

if filtered.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ---------------- Metric choice for chart ----------------
metric_labels = {
    "quantity_kg": "Import quantity (kg)",
    "value_bht": "Import value (THB)",
    "ai_kg": "Active ingredient (kg)",
    "price_thb": "Average price (THB/kg)",
}
metric_choice = st.radio(
    "Metric", list(metric_labels.keys()), format_func=lambda k: metric_labels[k], horizontal=True
)

# ---------------- Trend chart (line, split by chemical) ----------------
st.subheader(f"{metric_labels[metric_choice]} by year")

group_cols = ["year", "common_name"] if sel_names else ["year"]

if metric_choice == "price_thb":
    trend = filtered.groupby(group_cols, as_index=False)["price_thb"].mean()
    y_col = "price_thb"
else:
    trend = filtered.groupby(group_cols, as_index=False)[metric_choice].sum()
    y_col = metric_choice

if sel_names:
    # one or more chemicals picked -> a line per chemical
    fig = px.line(
        trend,
        x="year",
        y=y_col,
        color="common_name",
        markers=True,
        labels={"year": "Year", y_col: metric_labels[metric_choice], "common_name": "Chemical"},
    )
else:
    # no chemical picked -> single aggregate line (505 chemicals would be unreadable split out)
    fig = px.line(
        trend, x="year", y=y_col, markers=True, labels={"year": "Year", y_col: metric_labels[metric_choice]}
    )
    st.caption("Pick one or more chemicals above to split this line by chemical.")
st.plotly_chart(fig, width='stretch')

# ---------------- Breakdown by origin ----------------
st.subheader(f"{metric_labels[metric_choice]} by origin country")

if metric_choice == "price_thb":
    by_origin = filtered.groupby("origin", as_index=False)["price_thb"].mean()
else:
    by_origin = filtered.groupby("origin", as_index=False)[metric_choice].sum()
by_origin = by_origin.sort_values(metric_choice, ascending=False).head(15)

fig2 = px.bar(
    by_origin,
    x=metric_choice,
    y="origin",
    orientation="h",
    labels={metric_choice: metric_labels[metric_choice], "origin": "Origin"},
)
fig2.update_layout(yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig2, width='stretch')

# ---------------- Data table ----------------
with st.expander("View filtered data"):
    st.dataframe(filtered.sort_values("year", ascending=False), width='stretch')
    st.download_button(
        "Download filtered data as CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "filtered_chemical_import.csv",
        "text/csv",
    )
