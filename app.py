import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

## Part1
# ==================================================
# Page Configuration
# ==================================================
st.set_page_config(
    page_title="Chemical Dashboard",
    layout="wide"
)

st.title("🧪 Argicultural Chemical Import Volume (liter/kg) Dashboard")
## reset and reload data
if st.button("🔄 Reload Latest Data"):
    st.cache_data.clear()
    st.rerun()

# ==================================================
# Load Data
# ==================================================
@st.cache_data
def load_data():

    import_df = pd.read_excel("chemical_import_2025.xlsx")
    reg_df = pd.read_excel("chemical_registration.xlsx")

    # Automatically detect year columns
    year_columns = [c for c in import_df.columns if isinstance(c, int)]

    # Convert year columns to numeric
    for col in year_columns:
        import_df[col] = (
            import_df[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.strip()
        )

        import_df[col] = pd.to_numeric(import_df[col], errors="coerce")

    return import_df, reg_df


df, reg_df = load_data()

# standarddize the column
reg_df["common_name"] = (
    reg_df["common_name"]
    .astype(str)
    .str.upper()
    .str.strip()
)

reg_df["formula_type"] = (
    reg_df["formula_type"]
    .astype(str)
    .str.upper()
    .str.strip()
)

reg_df["concentration"] = (
    reg_df["concentration"]
    .astype(str)
    .str.strip()
)

df["Common_Name"] = (
    df["Common_Name"]
    .astype(str)
    .str.upper()
    .str.strip()
)

df["Formula_Type"] = (
    df["Formula_Type"]
    .astype(str)
    .str.upper()
    .str.strip()
)

df["Concentration"] = (
    df["Concentration"]
    .astype(str)
    .str.strip()
)

# Conver expiry_date
reg_df["expiry_date"] = pd.to_datetime(
    reg_df["expiry_date"],
    errors="coerce"
)

# Automatically detect years
year_columns = sorted([c for c in df.columns if isinstance(c, int)])
year_column_config = {
    year: st.column_config.NumberColumn(
        str(year),
        format="%,.0f"
    )
    for year in year_columns
}


# add today 
today = pd.Timestamp.today().normalize()

reg_df["Current_Status"] = np.where(
    reg_df["expiry_date"] >= today,
    "ACTIVE",
    "EXPIRED"
)




## Part1
# ==================================================
# Total Import (All Countries)
# ==================================================
st.divider()
st.header("📊 Total Import by Chemical")

st.write(
    "This section summarizes the total import volume across **all origins** "
    "for a selected chemical and concentration."
)

# ==================================================
# Sidebar
# ==================================================
st.sidebar.header("Search")


# Chemical
chemical = st.sidebar.selectbox(
    "Chemical",
    sorted(df["Common_Name"].dropna().unique())
)

# Concentration (filtered by chemical)
concentration = st.sidebar.selectbox(
    "Concentration",
    sorted(
        df.loc[
            df["Common_Name"] == chemical,
            "Concentration"
        ].dropna().unique()
    )
)

# Formula Type (filtered by chemical + concentration)
formula = st.sidebar.selectbox(
    "Formula Type",
    sorted(
        df.loc[
            (df["Common_Name"] == chemical) &
            (df["Concentration"] == concentration),
            "Formula_Type"
        ].dropna().unique()
    )
)


# filters
filtered_total = df[
    (df["Common_Name"] == chemical) &
    (df["Formula_Type"] == formula) &
    (df["Concentration"] == concentration)
]

if filtered_total.empty:
    st.warning("No matching record found.")
    st.stop()

# add the product
active_products = reg_df[
    (reg_df["common_name"] == chemical) &
    (reg_df["formula_type"] == formula) &
    (reg_df["concentration"] == concentration) &
    (reg_df["Current_Status"] == "ACTIVE")
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

chemical_type = filtered_total.iloc[0]["Type"].upper()

k1, k2 ,k3= st.columns(3)

with k1:
    st.metric(
        "Total Import(liter/kg)",
        f"{total_import:,.0f}"
    )

with k2:
    st.metric(
        "Number of Origins",
        country_count
    )
    
with k3:
    st.metric(
        "Chemical Type",
        chemical_type
    )

# -----------------------------
# Display
# -----------------------------
chemical_type = filtered_total.iloc[0]["Type"]
left, right = st.columns([1, 2])

with left:

    st.subheader("Yearly Import(liter/kg)")

    st.dataframe(
        yearly_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Volume": st.column_config.NumberColumn(
                "Volume(liter/kg)",
                format="%,.0f"
            )
        }
    )
    
    
with right:

    fig_total = px.line(
        yearly_df,
        x="Year",
        y="Volume",
        markers=True,
        title=f"{chemical} ({formula} - {concentration})"
    )

    fig_total.update_layout(
        height=500,
        xaxis_title="Year",
        yaxis_title="Import Volume"
    )
    
    fig_total.update_traces(
    hovertemplate=
    "<b>Year:</b> %{x}<br>"
    "<b>Volume:</b> %{y:,.1f}<extra></extra>"
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
        use_container_width=True,
         column_config={
        "Total": st.column_config.NumberColumn(
            "Total Import(liter/kg)",
            format="%,.0f"
        )
    }
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
    
    fig_country.update_traces(
    hovertemplate=
    "<b>Year:</b> %{x}<br>"
    "<b>Volume:</b> %{y:,.1f}<extra></extra>"
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

# -----------------------------
# Company import table
# -----------------------------
st.divider()
st.subheader("Active Registered Products")

k1, k2 = st.columns(2)

with k1:
    st.metric("Active Products", len(active_products))

with k2:
    st.metric("Distributors", active_products["distributor"].nunique())

if active_products.empty:
    st.info("No active registered products found for this chemical.")
else:
    display_cols = [
        "commercial_name",
        "registration_number",
        "distributor",
        "origin",
        "expiry_date"
    ]

    st.dataframe(
    active_products[display_cols],
    hide_index=True,
    use_container_width=True,
    column_config={
        "expiry_date": st.column_config.DateColumn(
            "Expiry Date",
            format="YYYY-MM-DD"
        )
    }
)




# ==================================================
# Import Comparison by Type
# ==================================================
st.divider()
st.header("📊 Import Comparison by Type")

# Display names for chemical types
type_mapping = {
    "HER": "Herbicide",
    "FUN": "Fungicide",
    "INS": "Insecticide",
    "PGR": "Plant Growth Regulator",
    "FUM": "Fumigant",
    "ACR": "Acaricide",
    "BIO": "Biopesticide",
    "ROD": "Rodenticide",
    "NEM": "Nematicide",
    "mol": "Molluscicide",
    "synergist": "Synergist",
    "OTHER": "Other"
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
        use_container_width=True,
        column_config={
        col: st.column_config.NumberColumn(
            col,
            format="%,.0f"
        )
        for col in table.columns
    }
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
    
    fig.update_traces(
    hovertemplate=
    "<b>Year:</b> %{x}<br>"
    "<b>Volume:</b> %{y:,.1f}<extra></extra>"
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

fig2.update_traces(
    hovertemplate=
    "<b>Year:</b> %{x}<br>"
    "<b>Volume:</b> %{y:,.1f}<extra></extra>"
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
    "HER": "Herbicide",
    "FUN": "Fungicide",
    "INS": "Insecticide",
    "PGR": "Plant Growth Regulator",
    "FUM": "Fumigant",
    "ACR": "Acaricide",
    "BIO": "Biopesticide",
    "ROD": "Rodenticide",
    "NEM": "Nematicide",
    "mol": "Molluscicide",
    "synergist": "Synergist",
    "OTHER": "Other"
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
        use_container_width=True,
        column_config={
        "Value": st.column_config.NumberColumn(
            "Import Volume",
            format="%,.0f"
        ),
        "Market Share (%)": st.column_config.NumberColumn(
            "Market Share (%)",
            format="%.2f"
        )
    }
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
        texttemplate="%{text:,.0f}",  # <-- Labels on bars
        textposition="outside",
        hovertemplate=
        "<b>%{y}</b><br>"
        "Import Volume: %{x:,.0f}<extra></extra>"   # <-- Hover
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

