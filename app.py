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


@st.cache_data
def load_classifications():
    """IRAC (insecticides), HRAC (herbicides), FRAC (fungicides) mode-of-action
    tables, keyed by a normalized common_name for lookup."""
    tables = {}
    for system in ["irac", "hrac", "frac"]:
        sub = pd.read_excel(DATA_PATH, sheet_name=system)
        sub["_norm_name"] = sub["common_name"].astype(str).str.strip().str.lower()
        tables[system.upper()] = sub
    return tables


def classify_chemical(common_name, tables):
    """Look up a common_name (splitting on '+' for mixtures) against all three
    mode-of-action systems. Returns a list of dict rows, one per component/system hit."""
    rows = []
    for component in str(common_name).split("+"):
        comp_norm = component.strip().lower()
        if not comp_norm:
            continue
        for system, tbl in tables.items():
            hits = tbl[tbl["_norm_name"] == comp_norm]
            for _, hit in hits.iterrows():
                row = {
                    "Component": component.strip(),
                    "System": system,
                    "Physiological category": hit.get("physiological_category", ""),
                    "Mode of action": hit.get("mode_of_action", ""),
                    "Chemical class/group": hit.get("chemical_class", hit.get("chemical_group", "")),
                    "Code": str(hit.get("code", "")),
                }
                rows.append(row)
    return rows


df = load_data()
classification_tables = load_classifications()

st.title("🧪 Chemical Import Dashboard")
st.caption("Import volume by chemical, concentration, formulation, and origin country")

# ---------------- Sidebar: reload only ----------------
st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    load_data.clear()
    load_classifications.clear()
    st.rerun()

# ---------------- Filters (main area, fully cross-linked) ----------------
st.subheader("Filters")

FILTER_COLS = ["common_name", "concentration", "formulation_type", "origin"]
FILTER_LABELS = {
    "common_name": "Chemical (common name)",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "origin": "Origin country",
}
FILTER_KEYS = {c: f"sel_{c}" for c in FILTER_COLS}

year_min, year_max = int(df["year"].min()), int(df["year"].max())
year_range_current = st.session_state.get("sel_years", (year_min, year_max))


def options_for(col):
    """Options for `col`, narrowed by every OTHER filter's current selection
    (plus the year range) so any filter can narrow any other, in any order."""
    sub = df[(df["year"] >= year_range_current[0]) & (df["year"] <= year_range_current[1])]
    for other in FILTER_COLS:
        if other == col:
            continue
        other_sel = st.session_state.get(FILTER_KEYS[other], [])
        if other_sel:
            sub = sub[sub[other].isin(other_sel)]
    return sorted(sub[col].unique())


sel = {}
row1_col1, row1_col2 = st.columns(2)
row2_col1, row2_col2 = st.columns(2)
slots = {
    "common_name": row1_col1,
    "concentration": row1_col2,
    "formulation_type": row2_col1,
    "origin": row2_col2,
}

for col in FILTER_COLS:
    with slots[col]:
        opts = options_for(col)
        key = FILTER_KEYS[col]
        # drop any previously-selected values that no longer apply, so a
        # tighter set from another filter never crashes the widget
        if key in st.session_state:
            valid = [v for v in st.session_state[key] if v in opts]
            if valid != st.session_state[key]:
                st.session_state[key] = valid
        sel[col] = st.multiselect(FILTER_LABELS[col], opts, key=key)
        if len(opts) == 1:
            st.caption(f"Only one {FILTER_LABELS[col].lower()} matches the other filters.")

sel_names = sel["common_name"]
sel_conc = sel["concentration"]
sel_form = sel["formulation_type"]
sel_origin = sel["origin"]

sel_years = st.slider("Year range", year_min, year_max, (year_min, year_max), key="sel_years")

filtered = df[(df["year"] >= sel_years[0]) & (df["year"] <= sel_years[1])]
if sel_names:
    filtered = filtered[filtered["common_name"].isin(sel_names)]
if sel_conc:
    filtered = filtered[filtered["concentration"].isin(sel_conc)]
if sel_form:
    filtered = filtered[filtered["formulation_type"].isin(sel_form)]
if sel_origin:
    filtered = filtered[filtered["origin"].isin(sel_origin)]

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
    trend = filtered.groupby(group_cols, as_index=False)[["value_bht", "quantity_kg"]].sum()
    trend["price_thb"] = trend["value_bht"] / trend["quantity_kg"].replace(0, pd.NA)
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
    by_origin = filtered.groupby("origin", as_index=False)[["value_bht", "quantity_kg"]].sum()
    by_origin["price_thb"] = by_origin["value_bht"] / by_origin["quantity_kg"].replace(0, pd.NA)
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

# ---------------- Compare chemicals ----------------
st.divider()
st.subheader("Compare chemicals")
st.caption("Pick up to 10 chemicals to compare side by side, within the filters set above (concentration/formulation/origin/year).")

all_names_in_scope = sorted(df["common_name"].unique())
compare_sel = st.multiselect(
    "Chemicals to compare",
    all_names_in_scope,
    max_selections=10,
    key="compare_sel",
)

if compare_sel:
    # respect the same concentration/formulation/origin/year filters, but swap
    # in the comparison selection for the chemical dimension
    compare_base = df[(df["year"] >= sel_years[0]) & (df["year"] <= sel_years[1])]
    if sel_conc:
        compare_base = compare_base[compare_base["concentration"].isin(sel_conc)]
    if sel_form:
        compare_base = compare_base[compare_base["formulation_type"].isin(sel_form)]
    if sel_origin:
        compare_base = compare_base[compare_base["origin"].isin(sel_origin)]
    compare_base = compare_base[compare_base["common_name"].isin(compare_sel)]

    if compare_base.empty:
        st.warning("None of the selected chemicals have data under the current concentration/formulation/origin/year filters.")
    else:
        summary = compare_base.groupby("common_name", as_index=False).agg(
            total_quantity_kg=("quantity_kg", "sum"),
            total_value_bht=("value_bht", "sum"),
            total_ai_kg=("ai_kg", "sum"),
            origin_countries=("origin", "nunique"),
            first_year=("year", "min"),
            last_year=("year", "max"),
        )
        summary["avg_price_thb_per_kg"] = summary["total_value_bht"] / summary["total_quantity_kg"].replace(0, pd.NA)
        summary = summary.rename(columns={
            "common_name": "Chemical",
            "total_quantity_kg": "Total quantity (kg)",
            "total_value_bht": "Total value (THB)",
            "avg_price_thb_per_kg": "Avg price (THB/kg)",
            "total_ai_kg": "Total AI (kg)",
            "origin_countries": "# origin countries",
            "first_year": "First year",
            "last_year": "Last year",
        })
        summary = summary[[
            "Chemical", "Total quantity (kg)", "Total value (THB)", "Avg price (THB/kg)",
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

        # quick visual comparison alongside the table
        cmp_fig = px.bar(
            summary,
            x="Chemical",
            y="Total quantity (kg)",
            labels={"Chemical": "Chemical", "Total quantity (kg)": "Total quantity (kg)"},
        )
        st.plotly_chart(cmp_fig, width='stretch')

        # ---- IRAC / HRAC / FRAC classification, shown as detail only ----
        st.markdown("**Classification detail (IRAC / HRAC / FRAC)**")
        detail_rows = []
        for name in compare_sel:
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
        detail_df = pd.DataFrame(detail_rows)
        st.dataframe(detail_df, width='stretch', hide_index=True)
else:
    st.info("Select chemicals above to compare them.")
