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
    "Manufacturing country": "source_country",
    "Importer": "importer",
    "Distributor": "distributor",
}

# roles whose column lists several ";"-separated values per row, needing
# split-and-match rather than a plain equality check
MULTI_VALUE_ROLES = {"Manufacturer (source)", "Manufacturing country"}

DISPLAY_COLS = {
    "distributor": "Distributor",
    "source": "Source",
    "register": "Register",
    "importer": "Importer",
    "common_name": "Chemical",
    "concentration": "Concentration",
    "formulation_type": "Formulation type",
    "category": "Category",
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


@st.cache_data
def manufacturing_country_options(reg_df):
    """source_country lists the distinct manufacturing countries per row,
    semicolon-separated — split into individual, deduplicated country names.
    Unlike manufacturer, this field is clean (no spelling variants)."""
    parts = set()
    for cell in reg_df["source_country"].dropna():
        for part in str(cell).split(";"):
            part = part.strip()
            if part:
                parts.add(part)
    return sorted(parts)


def _has_exact_token(cell, value):
    """True if `value` is one of the ";"-separated tokens in `cell` — exact
    per-token match, not substring, so e.g. a short country/company name
    can't falsely match inside an unrelated longer one."""
    if pd.isna(cell):
        return False
    return value in [p.strip() for p in str(cell).split(";")]


def company_portfolio(reg_df, role, company, active_only):
    """Registrations attributable to `company` in the given `role`.
    Manufacturer and manufacturing-country list several values per row
    (";"-separated) and need a token match; importer/distributor are always
    single-valued and use plain equality."""
    col = ROLE_COLUMNS[role]
    view = not_expired(reg_df) if active_only else reg_df
    if role in MULTI_VALUE_ROLES:
        mask = view[col].apply(lambda c: _has_exact_token(c, company))
    else:
        mask = view[col] == company
    return view[mask]


def _exploded_by_role(reg_df, role):
    """reg_df with one row per entity for `role`: multi-value roles
    (manufacturer, manufacturing country) get split on ";" so each named
    entity is counted on its own, matching how manufacturer_options() and
    _has_exact_token() already treat that column elsewhere on this page."""
    col = ROLE_COLUMNS[role]
    view = reg_df.dropna(subset=["issued"])
    if role not in MULTI_VALUE_ROLES:
        return view[view[col] != ""]
    exploded = view.assign(**{col: view[col].str.split(";")}).explode(col)
    exploded[col] = exploded[col].str.strip()
    return exploded[exploded[col] != ""]


@st.cache_data
def first_seen_year(reg_df, role):
    """Each entity's first calendar year on record for `role` — the earliest
    issued date across every registration that names them. Registrations
    with no issued date can't place an entity in a year, so they're left out
    of this (they still count everywhere else on this page)."""
    col = ROLE_COLUMNS[role]
    view = _exploded_by_role(reg_df, role)
    return view.groupby(col)["issued"].min().dt.year


@st.cache_data
def entrants_by_year(reg_df, role):
    """Count of entities first seen in each year, for a history-wide trend —
    a rising bar means the market is attracting more new manufacturers/
    importers/distributors/countries that year; a falling one means fewer."""
    first_year = first_seen_year(reg_df, role)
    counts = first_year.value_counts().sort_index().reset_index()
    counts.columns = ["year", "new_entrants"]
    return counts


def new_entrants(reg_df, role, year):
    """Entities for `role` whose first-ever issued registration falls in
    `year`, with how many registrations they've filed in total (through the
    data's latest issued date, regardless of current active status), the
    actual chemical/concentration/formulation combos that make up their
    portfolio — the quickest way to spot what's about to launch — and how
    many categories that spans."""
    col = ROLE_COLUMNS[role]
    first_year = first_seen_year(reg_df, role)
    entrant_names = first_year[first_year == year].index

    cols = {role: [], "Chemicals": [], "Registrations filed": [], "Categories": []}
    if len(entrant_names) == 0:
        return pd.DataFrame(cols)

    view = _exploded_by_role(reg_df, role)
    view = view[view[col].isin(entrant_names)]
    for entity, sub in view.groupby(col):
        combos = sub[["common_name", "concentration", "formulation_type"]].drop_duplicates()
        chemicals = "; ".join(
            f"{row.common_name} ({row.concentration}, {row.formulation_type})" for row in combos.itertuples()
        )
        cols[role].append(entity)
        cols["Chemicals"].append(chemicals)
        cols["Registrations filed"].append(len(sub))
        cols["Categories"].append(sub["category"].nunique())
    return pd.DataFrame(cols).sort_values("Registrations filed", ascending=False)


def new_entrant_detail(reg_df, role, year):
    """Every registration behind new_entrants()'s counts, at chemical level —
    which product (chemical, concentration, formulation type), which
    category, which manufacturer (source), and which distributor it's coming
    through — so "70 new distributors" turns into "here's what each one is
    actually bringing"."""
    col = ROLE_COLUMNS[role]
    first_year = first_seen_year(reg_df, role)
    entrant_names = first_year[first_year == year].index
    if len(entrant_names) == 0:
        return pd.DataFrame()

    view = _exploded_by_role(reg_df, role)
    view = view[view[col].isin(entrant_names)]

    # base labels first, then `col` (the role's own column) is set last so it
    # always wins its own label — e.g. role == "Manufacturer (source)" means
    # col == "source", and without this ordering the generic "Source" label
    # below would clobber the role's own "Manufacturer (source)" header
    rename = {
        "distributor": "Distributor", "source": "Source", "common_name": "Chemical",
        "concentration": "Concentration", "formulation_type": "Formulation type",
        "category": "Category", "reg_no": "Reg. No.", "issued": "Issued",
    }
    rename[col] = role

    detail_cols = list(dict.fromkeys([col, "distributor", "source", "common_name", "concentration", "formulation_type", "category", "reg_no", "issued"]))
    out = view[detail_cols].rename(columns=rename)

    order = [c for c in dict.fromkeys([role, "Distributor", "Source", "Chemical", "Concentration", "Formulation type", "Category", "Reg. No.", "Issued"]) if c in out.columns]
    return out[order].sort_values([role, "Chemical"])


def render_new_entrants(reg_df, role):
    """History-wide new-entrant trend for `role`, plus a drill-down into any
    one year's entrants — independent of whichever single company is
    selected above on this page."""
    counts = entrants_by_year(reg_df, role)
    if counts.empty:
        st.info("No dated registrations on record to determine entry years.")
        return

    issued_min, issued_max = int(reg_df["issued"].dt.year.min()), int(reg_df["issued"].dt.year.max())
    spans = (reg_df["expire"] - reg_df["issued"]).dt.days / 365.25
    if issued_max - issued_min <= spans.median() + 1:
        st.warning(
            f"reg_no only has issued dates from {issued_min}–{issued_max}, spanning one registration-renewal "
            f"cycle (~{spans.median():.0f} years) — not full registration history. \"First seen\" here means "
            f"first registered or renewed *in this cycle*, not necessarily new to the market: a company "
            f"supplying since the 1990s and one that's brand-new both show up the year they happened to "
            f"register. Treat this as renewal-activity timing, not true market-entry intelligence."
        )

    fig = px.bar(
        counts, x="year", y="new_entrants",
        labels={"year": "Year", "new_entrants": f"New {role.lower()}s"},
    )
    st.plotly_chart(fig, width='stretch')

    years = sorted(counts["year"].unique(), reverse=True)
    chosen_year = st.selectbox("Year", years, key="entrants_year")
    entrants = new_entrants(reg_df, role, chosen_year)
    if entrants.empty:
        st.info(f"No new {role.lower()}s first registered in {chosen_year}.")
    else:
        st.caption(f"{len(entrants)} new {role.lower()}(s) first registered in {chosen_year}, ranked by how many registrations they've filed since.")
        st.dataframe(entrants, width='stretch', hide_index=True)

        detail = new_entrant_detail(reg_df, role, chosen_year)
        st.markdown(f"**What these new {role.lower()}s are bringing — {chosen_year}**")
        cat_counts = detail.drop_duplicates(subset=["Reg. No."])["Category"].value_counts().reset_index()
        cat_counts.columns = ["Category", "Registrations"]
        fig_cat = px.bar(
            cat_counts.sort_values("Registrations", ascending=True), x="Registrations", y="Category", orientation="h",
            labels={"Registrations": "New registrations", "Category": "Category"},
        )
        st.plotly_chart(fig_cat, width='stretch')
        st.caption("Counted once per registration, even for a role (like manufacturer) that can list several names on one registration.")

        st.dataframe(detail, width='stretch', hide_index=True)
        st.download_button(
            "Download new-entrant detail as CSV",
            detail.to_csv(index=False).encode("utf-8"),
            f"new_{role.lower().replace(' ', '_').replace('(', '').replace(')', '')}_{chosen_year}.csv",
            "text/csv",
            key="new_entrant_detail_download",
        )


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
