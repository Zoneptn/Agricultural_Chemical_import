import streamlit as st
import pandas as pd
import plotly.express as px

## Part1
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

## Part2
# ==================================================
# Total Import (All Countries)
# ==================================================
st.divider()
st.header("📊 Total Import by Chemical (All Countries)")

st.write(
    "This section summarizes the total import volume across **all origins** "
    "for a selected chemical and concentration."
)

# -----------------------------
# Search
# -----------------------------
col1, col2 = st.columns(2)

with col1:
    chemical_total = st.selectbox(
        "Chemical",
        sorted(df["Common_Name"].dropna().unique()),
        key="chemical_total"
    )

with col2:

    concentration_total = st.selectbox(
        "Concentration",
        sorted(
            df.loc[
                df["Common_Name"] == chemical_total,
                "Concentration"
            ].dropna().unique()
        ),
        key="concentration_total"
    )

# -----------------------------
# Filter
# -----------------------------
filtered_total = df[
    (df["Common_Name"] == chemical_total) &
    (df["Concentration"] == concentration_total)
]

# -----------------------------
# Sum all countries
# -----------------------------
yearly_total = (
    filtered_total[year_columns]
    .sum()
    .fillna(0)
)

yearly_df = pd.DataFrame({
    "Year": year_columns,
    "Volume": yearly_total.values
})

# -----------------------------
# KPI
# -----------------------------
total_import = yearly_df["Volume"].sum()

country_count = filtered_total["Origin"].nunique()

st.metric(
    "Total Import (All Countries)",
    f"{total_import:,.0f}"
)

st.caption(f"Number of Origins: {country_count}")

# -----------------------------
# Display
# -----------------------------
left, right = st.columns([1,2])

with left:

    st.subheader("Yearly Import")

    st.dataframe(
        yearly_df,
        hide_index=True,
        use_container_width=True
    )

with right:

    fig_total = px.line(
        yearly_df,
        x="Year",
        y="Volume",
        markers=True,
        title=f"{chemical_total} ({concentration_total})"
    )

    fig_total.update_layout(
        height=500,
        xaxis_title="Year",
        yaxis_title="Import Volume"
    )

    st.plotly_chart(
        fig_total,
        use_container_width=True
    )

# -----------------------------
# Country Breakdown
# -----------------------------
st.subheader("Origin Contribution")

country_total = (
    filtered_total
    .assign(Total=filtered_total[year_columns].sum(axis=1))
    .groupby("Origin", as_index=False)["Total"]
    .sum()
    .sort_values("Total", ascending=False)
)

left, right = st.columns([1,2])

with left:

    st.dataframe(
        country_total,
        hide_index=True,
        use_container_width=True
    )

with right:

    fig_country = px.bar(
        country_total,
        x="Origin",
        y="Total",
        title="Total Import by Origin"
    )

    fig_country.update_layout(
        height=500,
        xaxis_title="Origin",
        yaxis_title="Total Import"
    )

    st.plotly_chart(
        fig_country,
        use_container_width=True
    )

# -----------------------------
# Download
# -----------------------------
csv_total = yearly_df.to_csv(index=False).encode("utf-8")

st.download_button(
    "Download Total Import",
    csv_total,
    "total_import_all_countries.csv",
    "text/csv"
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

## Part 4 
# ==================================================
# Top N Chemicals by Type
# ==================================================
st.divider()
st.header("🏆 Top Chemicals by Type")

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

# -------------------------------------
# Filters
# -------------------------------------
c1, c2, c3 = st.columns(3)

with c1:

    selected_type_name = st.selectbox(
        "Chemical Type",
        list(type_mapping.values()),
        key="top_type"
    )

with c2:

    year_option = st.selectbox(
        "Year",
        ["All Years"] + year_columns,
        key="top_year"
    )

with c3:

    top_n = st.selectbox(
        "Top N",
        [5,10,15,20,25,30],
        index=1,
        key="top_n"
    )

# -------------------------------------
# Convert display name back to code
# -------------------------------------
reverse_mapping = {v:k for k,v in type_mapping.items()}

selected_type = reverse_mapping[selected_type_name]

# -------------------------------------
# Filter by type
# -------------------------------------
df_top = df[df["Type"] == selected_type].copy()

# -------------------------------------
# Calculate value
# -------------------------------------
if year_option == "All Years":

    df_top["Value"] = df_top[year_columns].sum(axis=1)

else:

    df_top["Value"] = df_top[year_option]

# -------------------------------------
# Group by Common Name
# (Automatically sums all origins,
# concentrations and formulations)
# -------------------------------------
top_table = (
    df_top
    .groupby("Common_Name", as_index=False)["Value"]
    .sum()
)

# -------------------------------------
# Remove zero imports
# -------------------------------------
top_table = top_table[
    top_table["Value"] > 0
]

# -------------------------------------
# Sort
# -------------------------------------
top_table = (
    top_table
    .sort_values("Value", ascending=False)
    .head(top_n)
    .reset_index(drop=True)
)

# -------------------------------------
# Ranking
# -------------------------------------
top_table.index += 1
top_table.insert(0, "Rank", top_table.index)

# -------------------------------------
# Market Share
# -------------------------------------
grand_total = top_table["Value"].sum()

top_table["Market Share (%)"] = (
    top_table["Value"] /
    grand_total *
    100
).round(2)

# -------------------------------------
# KPI
# -------------------------------------
k1,k2,k3 = st.columns(3)

with k1:

    st.metric(
        "Top Chemical",
        top_table.iloc[0]["Common_Name"]
    )

with k2:

    st.metric(
        "Import Volume",
        f"{top_table.iloc[0]['Value']:,.0f}"
    )

with k3:

    st.metric(
        "Market Share",
        f"{top_table.iloc[0]['Market Share (%)']:.2f}%"
    )

# -------------------------------------
# Display
# -------------------------------------
left,right = st.columns([1,2])

with left:

    st.subheader("Ranking")

    st.dataframe(
        top_table,
        hide_index=True,
        use_container_width=True
    )

with right:

    fig = px.bar(
        top_table,
        x="Value",
        y="Common_Name",
        orientation="h",
        text="Value",
        title=f"Top {top_n} {selected_type_name}"
    )

    fig.update_layout(
        height=650,
        yaxis=dict(categoryorder="total ascending"),
        xaxis_title="Import Volume",
        yaxis_title=""
    )

    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

# -------------------------------------
# Download
# -------------------------------------
csv_top = top_table.to_csv(index=False).encode("utf-8")

st.download_button(
    "⬇ Download Ranking",
    csv_top,
    f"Top_{top_n}_{selected_type_name}.csv",
    "text/csv"
)

if st.button("🔄 Reload Latest Data"):
    st.cache_data.clear()
    st.rerun()