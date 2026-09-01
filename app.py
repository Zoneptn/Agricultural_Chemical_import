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

    # Normalize column names: strip whitespace / invisible characters
    # so a re-exported Excel file with slightly different header
    # formatting doesn't silently break every downstream lookup.
    # IMPORTANT: only touch columns that are already strings -- the
    # year columns (2020, 2021, ...) must stay as ints, since the
    # rest of the app detects them via isinstance(c, int).
    import_df.columns = [
        c.strip() if isinstance(c, str) else c for c in import_df.columns
    ]
    reg_df.columns = [
        c.strip() if isinstance(c, str) else c for c in reg_df.columns
    ]

    # Fail loudly (with a clear message) instead of a cryptic KeyError
    # deep in the app if the registration file schema doesn't match
    # what this dashboard expects.
    required_reg_cols = [
        "registration_number", "commercial_name", "common_name",
        "concentration", "formula_type", "origin", "applicant",
        "importer", "distributor", "registration_category",
        "issue_date", "expiry_date", "moa_group",
    ]
    missing_reg_cols = [c for c in required_reg_cols if c not in reg_df.columns]
    if missing_reg_cols:
        st.error(
            "chemical_registration.xlsx is missing expected column(s): "
            f"{missing_reg_cols}\n\nColumns found in file: {list(reg_df.columns)}"
        )
        st.stop()

    required_import_cols = [
        "Common_Name", "Concentration", "Formula_Type", "Origin", "Type",
    ]
    missing_import_cols = [c for c in required_import_cols if c not in import_df.columns]
    if missing_import_cols:
        st.error(
            "chemical_import_2025.xlsx is missing expected column(s): "
            f"{missing_import_cols}\n\nColumns found in file: {list(import_df.columns)}"
        )
        st.stop()

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

# ==========================================
# Cleaning Functions
# ==========================================
import re

def clean_common_name(x):
    x = str(x).upper()
    x = re.sub(r"\s+", " ", x)       # normalize whitespace
    x = re.sub(r"\s*\+\s*", "+", x)  # remove spaces around +
    x = re.sub(r"\s*-\s*", "-", x)   # remove spaces around -
    return x.strip()

# standarddize the column
reg_df["common_name"] = reg_df["common_name"].apply(clean_common_name)

reg_df["formula_type"] = (
    reg_df["formula_type"]
    .astype(str)
    .str.upper()
    .str.strip()
)

reg_df["concentration"] = (
    reg_df["concentration"]
    .astype(str)
    .str.upper()
    .str.strip()
)

df["Common_Name"] = df["Common_Name"].apply(clean_common_name)

df["Formula_Type"] = (
    df["Formula_Type"]
    .astype(str)
    .str.upper()
    .str.strip()
)

df["Concentration"] = (
    df["Concentration"]
    .astype(str)
    .str.upper()
    .str.strip()
)

# Conver expiry_date
# The registration data commonly stores dates using the Thai Buddhist
# Era (BE = CE + 543), e.g. "31/12/2568" instead of "31/12/2025".
# pandas can't parse a 4-digit year like 2568 directly (it's outside
# pandas' valid Timestamp range), so a straight pd.to_datetime() call
# fails on every single row -- which is exactly the symptom seen here.
def _parse_possibly_be_date(raw_series):
    # First, try a normal parse (covers files that are already Gregorian).
    parsed = pd.to_datetime(raw_series, errors="coerce", dayfirst=True)

    still_missing = parsed.isna() & raw_series.notna()

    if still_missing.any():
        raw_str = raw_series.astype(str).str.strip()

        def _convert_be(val):
            m = re.search(r"(\d{4})", val)
            if not m:
                return pd.NaT
            year = int(m.group(1))
            if year > 2200:  # clearly a Buddhist Era year, not Gregorian
                ce_year = year - 543
                val_ce = val.replace(m.group(1), str(ce_year), 1)
                return pd.to_datetime(val_ce, errors="coerce", dayfirst=True)
            return pd.to_datetime(val, errors="coerce", dayfirst=True)

        converted = raw_str[still_missing].apply(_convert_be)
        parsed.loc[still_missing] = converted

    return parsed

_raw_expiry_sample = (
    reg_df["expiry_date"].dropna().astype(str).head(5).tolist()
)

reg_df["expiry_date"] = _parse_possibly_be_date(reg_df["expiry_date"])

# Diagnostic: if a large share of expiry_date failed to parse, every
# row silently falls to "EXPIRED" and Active Registered Products will
# always be empty regardless of selection. Surface this instead of
# failing silently.
_unparsed_dates = reg_df["expiry_date"].isna().sum()
_total_reg_rows = len(reg_df)
if _total_reg_rows > 0 and (_unparsed_dates / _total_reg_rows) > 0.3:
    st.warning(
        f"⚠️ {_unparsed_dates} of {_total_reg_rows} rows in "
        "chemical_registration.xlsx still have an expiry_date that "
        "could not be parsed, even after trying a Thai Buddhist Era "
        "(BE) conversion. These rows are treated as EXPIRED.\n\n"
        f"Sample raw values from the column: {_raw_expiry_sample}"
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
# Total Import
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

# --------------------------------------------------
# Chemical
# --------------------------------------------------

chemical = st.sidebar.selectbox(
    "Chemical",
    sorted(df["Common_Name"].dropna().unique())
)

# --------------------------------------------------
# Concentration
# --------------------------------------------------

concentration = st.sidebar.selectbox(
    "Concentration",
    sorted(
        df.loc[
            df["Common_Name"] == chemical,
            "Concentration"
        ].dropna().unique()
    )
)

# --------------------------------------------------
# Formula Type
# --------------------------------------------------

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

# --------------------------------------------------
# Country / Origin
# --------------------------------------------------

countries = sorted(
    df.loc[
        (df["Common_Name"] == chemical) &
        (df["Concentration"] == concentration) &
        (df["Formula_Type"] == formula),
        "Origin"
    ].dropna().unique()
)

selected_country = st.sidebar.selectbox(
    "Country",
    ["All Countries"] + countries
)

# ==================================================
# Filter Chemical + Concentration + Formula
# ==================================================

filtered_total = df[
    (df["Common_Name"] == chemical) &
    (df["Formula_Type"] == formula) &
    (df["Concentration"] == concentration)
]

if filtered_total.empty:
    st.warning("No matching record found.")
    st.stop()

# ==================================================
# Active Registered Products
# ==================================================

active_products = reg_df[
    (reg_df["common_name"] == chemical) &
    (reg_df["formula_type"] == formula) &
    (reg_df["concentration"] == concentration) &
    (reg_df["Current_Status"] == "ACTIVE")
]

# Diagnostic: distinguish "no matching registration record at all" from
# "matching record(s) exist but are all marked EXPIRED" -- these need
# different fixes (data linkage vs. date parsing).
_matches_any_status = reg_df[
    (reg_df["common_name"] == chemical) &
    (reg_df["formula_type"] == formula) &
    (reg_df["concentration"] == concentration)
]
if active_products.empty and not _matches_any_status.empty:
    st.info(
        f"ℹ️ Found {len(_matches_any_status)} record(s) in "
        "chemical_registration.xlsx matching this chemical / formula / "
        "concentration, but all are marked EXPIRED (or have an "
        "unparsed expiry date). Nothing to show as 'active'."
    )
elif active_products.empty and _matches_any_status.empty:
    st.info(
        "ℹ️ No record in chemical_registration.xlsx matches this "
        f"combination: common_name='{chemical}', formula_type='{formula}', "
        f"concentration='{concentration}'. Check that these values are "
        "spelled/formatted the same way in both files."
    )

    # Show exactly what's in each file for this chemical so the
    # mismatch (spacing, symbols, abbreviations, etc.) is visible
    # instead of guessed at.
    with st.expander("🔍 Debug: compare values between the two files"):

        st.write(f"**Selected in sidebar (from chemical_import_2025.xlsx):**")
        st.write(
            f"- common_name: `{chemical}`\n"
            f"- formula_type: `{formula}`\n"
            f"- concentration: `{concentration}`"
        )

        reg_same_name = reg_df[reg_df["common_name"] == chemical]

        if reg_same_name.empty:
            # Try a loose, case/space-insensitive match to see if the
            # chemical exists under a slightly different spelling.
            loose = reg_df[
                reg_df["common_name"].str.replace(" ", "", regex=False)
                == chemical.replace(" ", "")
            ]
            st.write(
                f"No rows in chemical_registration.xlsx have "
                f"common_name == `{chemical}` at all."
            )
            if not loose.empty:
                st.write(
                    "But found close matches ignoring spaces -- "
                    "here's how common_name is actually spelled in "
                    "the registration file:"
                )
                st.write(sorted(loose["common_name"].unique().tolist()))
            else:
                st.write(
                    "No close match either. Here are some sample "
                    "common_name values that *do* exist in "
                    "chemical_registration.xlsx, for comparison:"
                )
                st.write(sorted(reg_df["common_name"].dropna().unique().tolist())[:30])
        else:
            st.write(
                f"Found {len(reg_same_name)} row(s) in "
                "chemical_registration.xlsx with matching common_name. "
                "Their formula_type / concentration values are:"
            )
            st.dataframe(
                reg_same_name[["formula_type", "concentration"]]
                .drop_duplicates()
                .reset_index(drop=True),
                use_container_width=True
            )
            st.write(
                "Compare these against the sidebar values above -- "
                "look for extra/missing spaces, % signs, or different "
                "abbreviations."
            )

# ==================================================
# Total Import - All Countries
# ==================================================

yearly_total = (
    filtered_total[year_columns]
    .sum()
    .fillna(0)
)

yearly_df = pd.DataFrame({
    "Year": year_columns,
    "Volume": yearly_total.values
})

# ==================================================
# Country Import by Year
# ==================================================

if selected_country == "All Countries":

    # Sum all countries together
    chart_yearly_df = pd.DataFrame({
        "Year": year_columns,
        "Volume": (
            filtered_total[year_columns]
            .sum()
            .fillna(0)
            .values
        )
    })

else:

    # Import from selected country only
    selected_country_data = filtered_total[
        filtered_total["Origin"] == selected_country
    ]

    chart_yearly_df = pd.DataFrame({
        "Year": year_columns,
        "Volume": (
            selected_country_data[year_columns]
            .sum()
            .fillna(0)
            .values
        )
    })



# ==================================================
# KPI
# ==================================================

total_import = yearly_df["Volume"].sum()

country_count = filtered_total["Origin"].nunique()

chemical_type = filtered_total.iloc[0]["Type"].upper()

k1, k2, k3 = st.columns(3)

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

# ==================================================
# Yearly Import + Line Chart
# ==================================================

left, right = st.columns([1, 2])

# --------------------------------------------------
# Table
# --------------------------------------------------

with left:

    if selected_country == "All Countries":

        st.subheader("Yearly Import - All Countries")

    else:

        st.subheader(
            f"Yearly Import - {selected_country}"
        )

    st.dataframe(
        chart_yearly_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Volume": st.column_config.NumberColumn(
                "Volume(liter/kg)",
                format="%,.0f"
            )
        }
    )

# --------------------------------------------------
# Line Chart
# --------------------------------------------------
with right:

    if selected_country == "All Countries":

        chart_title = (
            f"{chemical} ({formula} - {concentration}) "
            "— All Countries"
        )

    else:

        chart_title = (
            f"{chemical} ({formula} - {concentration}) "
            f"— {selected_country}"
        )

    fig_total = px.line(
        chart_yearly_df,
        x="Year",
        y="Volume",
        markers=True,
        title=chart_title
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

# ==================================================
# Country Breakdown
# ==================================================

st.subheader("Origin Contribution")

country_total = (
    filtered_total
    .assign(
        Total=filtered_total[year_columns].sum(axis=1)
    )
    .groupby(
        "Origin",
        as_index=False
    )["Total"]
    .sum()
    .sort_values(
        "Total",
        ascending=False
    )
)

left, right = st.columns([1, 2])

# --------------------------------------------------
# Country Table
# --------------------------------------------------

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

# --------------------------------------------------
# Country Bar Chart
# --------------------------------------------------

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
        "<b>Country:</b> %{x}<br>"
        "<b>Volume:</b> %{y:,.1f}<extra></extra>"
    )

    st.plotly_chart(
        fig_country,
        use_container_width=True
    )

# ==================================================
# Download
# ==================================================

csv_total = yearly_df.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    "Download Total Import",
    csv_total,
    "total_import_all_countries.csv",
    "text/csv"
)

# ==================================================
# Company Import Table
# ==================================================

st.divider()
st.subheader("Active Registered Products")

k1, k2 = st.columns(2)

with k1:
    st.metric(
        "Active Products",
        len(active_products)
    )

with k2:
    st.metric(
        "Distributors",
        active_products["distributor"].nunique()
    )

if active_products.empty:

    st.info(
        "No active registered products found for this chemical."
    )

else:

    display_cols = [
        "registration_number",
        "commercial_name",
        "distributor",
        "origin",
        "applicant",
        "expiry_date"
    ]

    st.dataframe(
        active_products[display_cols],
        hide_index=True,
        use_container_width=True,
        column_config={
            "expiry_date": st.column_config.DateColumn(
                "Expiry Date",
                format="DD-MM-YYYY"
            )
        }
    )
# ==================================================
# Chemical Comparison
# ==================================================

st.divider()
st.header("📈 Chemical Comparison")

st.write(
    "Compare import volumes for up to 10 chemical products."
)

# ----------------------------------------
# Number of chemicals
# ----------------------------------------

num_compare = st.slider(
    "Number of Chemicals to Compare",
    min_value=2,
    max_value=10,
    value=2
)

compare_data = []

# ----------------------------------------
# Selection boxes
# ----------------------------------------

for i in range(num_compare):

    st.subheader(f"Chemical {i+1}")

    col1, col2, col3, col4 = st.columns(4)

    # ----------------------------------------
    # Common Name
    # ----------------------------------------

    with col1:

        chemical_i = st.selectbox(
            "Common Name",
            sorted(
                df["Common_Name"]
                .dropna()
                .unique()
            ),
            key=f"chemical_{i}"
        )

    # ----------------------------------------
    # Concentration
    # ----------------------------------------

    with col2:

        concentration_i = st.selectbox(
            "Concentration",
            sorted(
                df.loc[
                    df["Common_Name"] == chemical_i,
                    "Concentration"
                ]
                .dropna()
                .unique()
            ),
            key=f"conc_{i}"
        )

    # ----------------------------------------
    # Formula Type
    # ----------------------------------------

    with col3:

        formula_i = st.selectbox(
            "Formula Type",
            sorted(
                df.loc[
                    (df["Common_Name"] == chemical_i) &
                    (df["Concentration"] == concentration_i),
                    "Formula_Type"
                ]
                .dropna()
                .unique()
            ),
            key=f"formula_{i}"
        )

    # ----------------------------------------
    # Country
    # ----------------------------------------

    with col4:

        countries_i = sorted(
            df.loc[
                (df["Common_Name"] == chemical_i) &
                (df["Concentration"] == concentration_i) &
                (df["Formula_Type"] == formula_i),
                "Origin"
            ]
            .dropna()
            .unique()
        )

        country_i = st.selectbox(
            "Country",
            ["All Countries"] + countries_i,
            key=f"country_{i}"
        )

    # ----------------------------------------
    # Filter
    # ----------------------------------------

    temp = df[
        (df["Common_Name"] == chemical_i) &
        (df["Concentration"] == concentration_i) &
        (df["Formula_Type"] == formula_i)
    ]

    # ----------------------------------------
    # Country filter
    # ----------------------------------------

    if country_i != "All Countries":

        temp = temp[
            temp["Origin"] == country_i
        ]

    # ----------------------------------------
    # Create yearly data
    # ----------------------------------------

    if not temp.empty:

        yearly = (
            temp[year_columns]
            .sum()
            .fillna(0)
        )

        temp_df = pd.DataFrame({
            "Year": year_columns,
            "Volume": yearly.values
        })

        # ----------------------------------------
        # Label for chart
        # ----------------------------------------

        if country_i == "All Countries":

            chemical_label = (
                chemical_i +
                " | " +
                concentration_i +
                " | " +
                formula_i +
                " | All Countries"
            )

        else:

            chemical_label = (
                chemical_i +
                " | " +
                concentration_i +
                " | " +
                formula_i +
                " | " +
                country_i
            )

        temp_df["Chemical"] = chemical_label

        compare_data.append(temp_df)

# ==================================================
# Plot
# ==================================================

if compare_data:

    compare_df = pd.concat(
        compare_data,
        ignore_index=True
    )

    fig_compare = px.line(
        compare_df,
        x="Year",
        y="Volume",
        color="Chemical",
        markers=True,
        template="plotly_white"
    )

    fig_compare.update_layout(
        title="Chemical Import Comparison",
        xaxis_title="Year",
        yaxis_title="Import Volume",
        hovermode="x unified",
        legend_title="Chemical",
        height=650
    )

    fig_compare.update_yaxes(
        tickformat=","
    )

    fig_compare.update_traces(
        hovertemplate=
        "<b>%{fullData.name}</b><br>" +
        "Year: %{x}<br>" +
        "Volume: %{y:,.1f}<extra></extra>"
    )

    st.plotly_chart(
        fig_compare,
        use_container_width=True
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
