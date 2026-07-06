import streamlit as st
import pandas as pd
import plotly.express as px

# ==================================================
# Page Configuration
# ==================================================
st.set_page_config(
    page_title="Chemical Dashboard",
    layout="wide"
)

st.title("🧪 Argicultural Chemical Import Volume (litre/kg) Dashboard")

# ==================================================
# Load Data
# ==================================================
@st.cache_data
def load_data():
    df = pd.read_excel("chemical_import_2025.xlsx")

    # Automatically detect year columns
    year_columns = [c for c in df.columns if isinstance(c, int)]

    # Convert year columns to numeric
    for col in year_columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.strip()
        )

        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


df = load_data()

# Automatically detect years
year_columns = sorted([c for c in df.columns if isinstance(c, int)])

# ==================================================
# Sidebar Filters
# ==================================================
st.sidebar.header("Search")

chemical = st.sidebar.selectbox(
    "Chemical Name",
    sorted(df["Common_Name"].dropna().unique())
)

formula = st.sidebar.selectbox(
    "Formula Type",
    sorted(
        df.loc[
            df["Common_Name"] == chemical,
            "Formula_Type"
        ].dropna().unique()
    )
)

concentration = st.sidebar.selectbox(
    "Concentration",
    sorted(
        df.loc[
            (df["Common_Name"] == chemical) &
            (df["Formula_Type"] == formula),
            "Concentration"
        ].dropna().unique()
    )
)

origin = st.sidebar.selectbox(
    "Origin",
    sorted(
        df.loc[
            (df["Common_Name"] == chemical) &
            (df["Formula_Type"] == formula) &
            (df["Concentration"] == concentration),
            "Origin"
        ].dropna().unique()
    )
)

# ==================================================
# Filter Data
# ==================================================
filtered = df[
    (df["Common_Name"] == chemical) &
    (df["Formula_Type"] == formula) &
    (df["Concentration"] == concentration) &
    (df["Origin"] == origin)
]

if filtered.empty:
    st.warning("No matching record found.")
    st.stop()

row = filtered.iloc[0]

# ==================================================
# Chemical Information
# ==================================================
st.subheader("Chemical Information")

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Chemical", row["Common_Name"])
c2.metric("Formula", row["Formula_Type"])
c3.metric("Concentration", row["Concentration"])
c4.metric("Origin", row["Origin"])
c5.metric("Type", row["Type"])

# ==================================================
# Yearly Volume Table
# ==================================================
yearly = pd.DataFrame({
    "Year": year_columns,
    "Volume": [row[y] for y in year_columns]
})

yearly["Volume"] = pd.to_numeric(
    yearly["Volume"],
    errors="coerce"
).fillna(0)

# ==================================================
# Display
# ==================================================
st.subheader("Yearly Volume")

left, right = st.columns([1, 2])

with left:

    st.dataframe(
        yearly,
        hide_index=True,
        use_container_width=True
    )

    total_volume = yearly["Volume"].sum()

    st.metric(
        "Total Volume",
        f"{total_volume:,.0f}"
    )

with right:

    fig = px.line(
        yearly,
        x="Year",
        y="Volume",
        markers=True,
        title="Volume Trend"
    )

    fig.update_layout(
        height=500,
        xaxis_title="Year",
        yaxis_title="Volume"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

# ==================================================
# Selected Record
# ==================================================
st.subheader("Selected Record")

st.dataframe(
    filtered,
    use_container_width=True
)

# ==================================================
# Download
# ==================================================
csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download Selected Record",
    data=csv,
    file_name="chemical_result.csv",
    mime="text/csv"
)

# ==================================================
# Import Comparison by Type
# ==================================================
st.divider()
st.header("📊 Import Comparison by Type")

# Display names for chemical types
type_mapping = {
    "her": "Herbicide",
    "fun": "Fungicide",
    "ins": "Insecticide",
    "pgr": "Plant Growth Regulator",
    "fum": "Fumigant",
    "acr": "Acaricide",
    "bio": "Biopesticide",
    "rod": "Rodenticide",
    "nem": "Nematicide",
    "mol": "Molluscicide",
    "synergist": "Synergist",
    "other": "Other"
}

# Create comparison dataframe
comparison = (
    df.groupby("Type")[year_columns]
      .sum(numeric_only=True)
      .reset_index()
)

comparison["Type_Name"] = comparison["Type"].map(type_mapping)

# -----------------------------
# Select types to compare
# -----------------------------
selected_types = st.multiselect(
    "Select chemical types",
    comparison["Type_Name"].tolist(),
    default=["Herbicide", "Fungicide", "Insecticide"]
)

comparison = comparison[
    comparison["Type_Name"].isin(selected_types)
]

# -----------------------------
# Convert to long format
# -----------------------------
comparison_long = comparison.melt(
    id_vars=["Type", "Type_Name"],
    value_vars=year_columns,
    var_name="Year",
    value_name="Import Volume"
)

comparison_long["Import Volume"] = comparison_long["Import Volume"].fillna(0)

# -----------------------------
# KPI
# -----------------------------
total_import = comparison_long["Import Volume"].sum()

st.metric(
    "Total Import Volume",
    f"{total_import:,.0f}"
)

# -----------------------------
# Table + Charts
# -----------------------------
left, right = st.columns([1,2])

with left:

    table = comparison_long.pivot(
        index="Year",
        columns="Type_Name",
        values="Import Volume"
    ).fillna(0)

    st.dataframe(
        table,
        use_container_width=True
    )

with right:

    fig = px.line(
        comparison_long,
        x="Year",
        y="Import Volume",
        color="Type_Name",
        markers=True,
        title="Import Volume by Chemical Type"
    )

    fig.update_layout(
        height=550,
        xaxis_title="Year",
        yaxis_title="Import Volume"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

# -----------------------------
# Stacked Bar Chart
# -----------------------------
st.subheader("Stacked Comparison")

fig2 = px.bar(
    comparison_long,
    x="Year",
    y="Import Volume",
    color="Type_Name",
    title="Total Import Volume by Year",
    barmode="stack"
)

fig2.update_layout(
    height=600,
    xaxis_title="Year",
    yaxis_title="Import Volume"
)

st.plotly_chart(
    fig2,
    use_container_width=True
)

# -----------------------------
# Download
# -----------------------------
csv_compare = table.reset_index().to_csv(index=False).encode("utf-8")

st.download_button(
    "Download Comparison Table",
    csv_compare,
    "type_comparison.csv",
    "text/csv"
)